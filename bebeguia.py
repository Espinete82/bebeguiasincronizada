import streamlit as st
import streamlit.components.v1 as components
import datetime
from datetime import timedelta
import json
import copy
from supabase import create_client

st.set_page_config(page_title="BebéGuía", page_icon="🌙", layout="centered")

# ─── SUPABASE CLIENT ──────────────────────────────────────────
@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

RECORD_ID = 1  # Una sola fila compartida para toda la familia

# ─── TIMEZONE ─────────────────────────────────────────────────
def now_local():
    offset = st.session_state.get('utc_offset', 1)
    return datetime.datetime.utcnow() + timedelta(hours=offset)

# ─── SERIALIZACIÓN ────────────────────────────────────────────
def _serialize(state_dict):
    """Convierte el estado a JSON serializable."""
    s = copy.deepcopy(state_dict)
    if s.get('baby') and s['baby'].get('birth'):
        birth = s['baby']['birth']
        if hasattr(birth, 'strftime'):
            s['baby']['birth'] = birth.strftime("%Y-%m-%d")
    for log in s.get('logs', []):
        if hasattr(log.get('ts'), 'isoformat'):
            log['ts'] = log['ts'].isoformat()
    for key in ('phaseStart', 'pause_start'):
        if s.get(key) and hasattr(s[key], 'isoformat'):
            s[key] = s[key].isoformat()
    return s

def _deserialize(data):
    """Convierte datos de Supabase al estado de la app."""
    if not data or not data.get('baby'):  # FIX: {} sin baby no es estado válido
        return None
    if data.get('baby', {}).get('birth'):
        data['baby']['birth'] = datetime.datetime.strptime(
            data['baby']['birth'], "%Y-%m-%d").date()
    for log in data.get('logs', []):
        if isinstance(log.get('ts'), str):
            log['ts'] = datetime.datetime.fromisoformat(log['ts'])
    for key in ('phaseStart', 'pause_start'):
        if data.get(key) and isinstance(data[key], str):
            data[key] = datetime.datetime.fromisoformat(data[key])
    return data

# ─── PERSISTENCIA EN SUPABASE ─────────────────────────────────
def load_data():
    try:
        sb = get_supabase()
        res = sb.table("bebe_state").select("*").eq("id", RECORD_ID).execute()
        if res.data:
            raw = res.data[0].get("state", {})
            if isinstance(raw, str):
                raw = json.loads(raw)
            return _deserialize(raw)
        return None
    except Exception as e:
        st.warning(f"No se pudo cargar datos: {e}")
        return None

def save_data():
    s = {
        'baby':            st.session_state.baby,
        'logs':            st.session_state.logs,
        'phase':           st.session_state.phase,
        'phaseStart':      st.session_state.phaseStart,
        'utc_offset':      st.session_state.get('utc_offset', 1),
        'dw_start':        st.session_state.get('dw_start', 21),
        'dw_end':          st.session_state.get('dw_end', 3),
        'work_hour':       st.session_state.get('work_hour', 7),
        'papa_mode':       st.session_state.get('papa_mode', '💼 Trabajando'),
        'timer_paused':    st.session_state.get('timer_paused', False),
        'paused_seconds':  st.session_state.get('paused_seconds', 0),
        'pause_start':     st.session_state.get('pause_start'),
    }
    serialized = _serialize(s)
    try:
        sb = get_supabase()
        sb.table("bebe_state").upsert({"id": RECORD_ID, "state": serialized}).execute()
    except Exception as e:
        st.warning(f"No se pudo guardar: {e}")

# ─── INICIALIZACIÓN ───────────────────────────────────────────
if 'initialized' not in st.session_state:
    db = load_data()
    if db:
        st.session_state.baby            = db.get('baby')
        st.session_state.logs            = db.get('logs', [])
        st.session_state.phase           = db.get('phase', 'idle')
        st.session_state.phaseStart      = db.get('phaseStart')
        st.session_state.utc_offset      = db.get('utc_offset', 1)
        st.session_state.dw_start        = db.get('dw_start', 21)
        st.session_state.dw_end          = db.get('dw_end', 3)
        st.session_state.work_hour       = db.get('work_hour', 7)
        st.session_state.papa_mode       = db.get('papa_mode', '💼 Trabajando')
        st.session_state.timer_paused    = db.get('timer_paused', False)
        st.session_state.paused_seconds  = db.get('paused_seconds', 0)
        st.session_state.pause_start     = db.get('pause_start')
        st.session_state.last_completed  = None  # FIX: siempre inicializar
        st.session_state.page            = "main" if db.get('baby') else "setup"
    else:
        st.session_state.baby            = None
        st.session_state.logs            = []
        st.session_state.phase           = "idle"
        st.session_state.phaseStart      = None
        st.session_state.utc_offset      = 1
        st.session_state.dw_start        = 21
        st.session_state.dw_end          = 3
        st.session_state.work_hour       = 7
        st.session_state.papa_mode       = '💼 Trabajando'
        st.session_state.timer_paused    = False
        st.session_state.paused_seconds  = 0
        st.session_state.pause_start     = None
        st.session_state.last_completed  = None
        st.session_state.page            = "setup"
    st.session_state.initialized = True

# ─── HELPERS ──────────────────────────────────────────────────
def age_days():
    b = st.session_state.baby
    if not b or not b.get('birth'):
        return 0
    # FIX: usar fecha local, no UTC, para que el día no cambie a medianoche UTC
    local_today = now_local().date()
    return (local_today - b['birth']).days

def age_weeks():
    return age_days() // 7

def get_aw_range(days):
    w = days // 7
    if w < 2:  return 45,  75
    if w < 4:  return 50,  80
    if w < 8:  return 60,  90
    if w < 12: return 75, 105
    if w < 16: return 90, 120
    if w < 24: return 105, 150
    return 120, 180

def get_sleep_range(days, is_night):
    w = days // 7
    if is_night:
        if w < 2:  return  90, 150, "1.5–2.5h"
        if w < 4:  return 110, 180, "2–3h"
        if w < 8:  return 135, 210, "2.5–3.5h"
        if w < 12: return 150, 300, "2.5–5h"
        if w < 16: return 180, 360, "3–6h"
        return          240, 420, "4–7h"
    else:
        if w < 2:  return  20,  60, "20–60 min"
        if w < 4:  return  30,  70, "30–70 min"
        if w < 8:  return  30, 120, "30min–2h"
        if w < 12: return  45,  90, "45–90 min"
        if w < 16: return  60,  90, "1–1.5h"
        return           60, 120, "1–2h"

def get_sleep_durations(days, is_night):
    lo, hi, lbl = get_sleep_range(days, is_night)
    avg = (lo + hi) // 2
    return avg, lbl

def get_feed_range(days):
    if "materna" in (st.session_state.baby or {}).get('feed', '').lower():
        return 10, 30
    return 10, 25

def get_aw_max(days):
    return get_aw_range(days)[1]

# ─── EVALUACIÓN DE DURACIÓN REAL ──────────────────────────────
def assess_log(log_type, dur_min, ts, days):
    """
    Retorna (emoji_estado, color_fondo, color_borde, texto_valoracion, rango_label)
    comparando la duración real contra el rango esperado para la edad.
    """
    if log_type == "feeding":
        lo, hi = get_feed_range(days)
        rango = f"{lo}–{hi} min"
        if dur_min < lo:
            return "⚡", "#FEF3C7", "#F59E0B", f"Toma corta ({dur_min} min) — puede que no haya vaciado bien. Observa si pide antes de lo esperado.", rango
        elif dur_min > hi:
            return "🐢", "#EDE9FE", "#8B5CF6", f"Toma larga ({dur_min} min) — puede que esté usando el pecho/biberón de chupete o tenga dificultad de agarre.", rango
        else:
            return "✅", "#F0FDF4", "#22C55E", f"Duración perfecta ({dur_min} min). Dentro del rango esperado.", rango

    elif log_type == "sleeping":
        h = ts.hour
        is_night = h >= 20 or h < 7
        lo, hi, lbl = get_sleep_range(days, is_night)
        tipo = "nocturno" if is_night else "diurno"
        rango = lbl
        if dur_min < lo:
            return "😓", "#FEF3C7", "#F59E0B", f"Sueño {tipo} corto ({dur_min} min, esperado {lbl}). ¿Ruido? ¿Hambre? ¿Demasiado calor/frío?", rango
        elif dur_min > hi:
            label_largo = "✅ Estupendo" if is_night else "⚠️ Siesta muy larga — puede afectar el sueño nocturno"
            color_f = "#F0FDF4" if is_night else "#FEF3C7"
            color_b = "#22C55E" if is_night else "#F59E0B"
            return ("🌙" if is_night else "⚠️"), color_f, color_b, f"{label_largo} ({dur_min} min, rango {lbl}).", rango
        else:
            return "✅", "#F0FDF4", "#22C55E", f"Sueño {tipo} dentro del rango ({dur_min} min, esperado {lbl}).", rango

    elif log_type == "activity":
        lo, hi = get_aw_range(days)
        rango = f"{lo}–{hi} min"
        if dur_min < lo:
            return "🌱", "#EFF6FF", "#3B82F6", f"Actividad corta ({dur_min} min) — normal si estaba somnoliento. La ventana mínima es {lo} min.", rango
        elif dur_min > hi:
            return "🚨", "#FEF2F2", "#EF4444", f"Actividad demasiado larga ({dur_min} min, máx {hi} min) — probablemente estuvo sobreestimulado. Signos: llanto, mirada perdida, puños cerrados.", rango
        else:
            return "✅", "#F0FDF4", "#22C55E", f"Actividad dentro de la ventana ({dur_min} min, rango {rango}).", rango

    # pañales y otros — sin valoración de duración
    return None, None, None, None, None

def elapsed_sec():
    """Segundos transcurridos en la fase actual, descontando tiempo pausado."""
    if not st.session_state.phaseStart:
        return 0
    total = (now_local() - st.session_state.phaseStart).total_seconds()
    paused = st.session_state.get('paused_seconds', 0)
    if st.session_state.get('timer_paused') and st.session_state.get('pause_start'):
        paused += (now_local() - st.session_state.pause_start).total_seconds()
    return max(0, int(total - paused))

def elapsed_min():
    return elapsed_sec() // 60

def add_log(log_type, dur_min=0, color=None, ts=None):
    """Añade un log. Si ts=None usa now_local() (tiempo real). Si ts se provee, es un log retroactivo."""
    log = {"type": log_type, "ts": ts if ts is not None else now_local(), "durMin": dur_min, "color": color}
    st.session_state.logs.append(log)
    st.session_state.logs.sort(key=lambda x: x['ts'])  # mantener orden cronológico
    save_data()

def change_phase(new_phase):
    dur = elapsed_min()
    # Registrar fase anterior siempre que haya un phaseStart válido y la fase no sea idle
    # Usamos dur >= 0 para capturar incluso cambios rápidos durante pruebas
    if st.session_state.phaseStart and st.session_state.phase not in ("idle",) and new_phase != st.session_state.phase:
        prev_phase = st.session_state.phase
        prev_start = st.session_state.phaseStart
        add_log(prev_phase, dur)
        # Guardar resumen para mostrar banner de confirmación
        emoji, bg, border, msg, rango = assess_log(prev_phase, dur, prev_start, age_days())
        st.session_state.last_completed = {
            "type": prev_phase, "dur": dur, "emoji": emoji,
            "bg": bg, "border": border, "msg": msg, "rango": rango,
            "hora": prev_start.strftime("%H:%M"),
        }
    else:
        st.session_state.last_completed = None
    st.session_state.phase          = new_phase
    st.session_state.phaseStart     = now_local()
    st.session_state.timer_paused   = False
    st.session_state.paused_seconds = 0
    st.session_state.pause_start    = None
    save_data()

# ─── LACTANCIA POR EDAD → ROL DE PAPÁ ─────────────────────────
def papa_feed_method(days, feed_type):
    weeks = days // 7
    if "materna" in feed_type.lower():
        if weeks < 2:
            return "🪡 Da calostro con jeringa o dedo (no biberón aún)"
        elif weeks < 4:
            return "👆 Alimentación con dedo (finger feeding) si mamá no puede"
        elif weeks < 6:
            return "🍼 Puede ofrecer leche extraída en biberón (flujo lento)"
        else:
            return "🍼 Da biberón con leche materna extraída"
    elif "mixta" in feed_type.lower():
        if weeks < 2:
            return "🪡 Jeringa o dedo con leche materna/fórmula"
        elif weeks < 4:
            return "👆 Finger feeding o biberón con tetina de flujo lento"
        else:
            return "🍼 Prepara y da biberón completo (fórmula o leche extraída)"
    else:
        return "🍼 Prepara y da biberón completo"

# ─── AGENDA EASY COMPLETA ─────────────────────────────────────
def build_agenda(baby, now, current_phase, sim_elapsed):
    days      = age_days()
    aw_max    = get_aw_max(days)
    feed_type = baby.get('feed', 'Mixta')
    is_fase1  = days < 120

    # ── Anclar en el último evento registrado si es más reciente que phaseStart ──
    # Esto permite que los eventos retroactivos actualicen el pronóstico
    recent_logs = [l for l in st.session_state.logs
                   if l['ts'] <= now and l['type'] in ("feeding", "sleeping", "activity")]
    if recent_logs:
        last_log = max(recent_logs, key=lambda x: x['ts'])
        last_end = last_log['ts'] + datetime.timedelta(minutes=last_log.get('durMin', 0))
        # Si el final del último log es más reciente que phaseStart, re-anclar
        phase_start = st.session_state.phaseStart or (now - datetime.timedelta(minutes=sim_elapsed))
        if last_end > phase_start and last_end <= now:
            current_phase = {
                "feeding":  "sleeping" if (now.hour >= 20 or now.hour < 7) else "activity",
                "sleeping": "feeding",
                "activity": "sleeping",
            }.get(last_log['type'], current_phase)
            sim_elapsed = int((now - last_end).total_seconds() / 60)

    cursor    = now
    limit     = now + datetime.timedelta(hours=24)
    agenda    = []
    MAX_ITER  = 80

    total_tomas   = 0
    mama_free_min = 0

    dw_s = st.session_state.get('dw_start', 21)
    dw_e = st.session_state.get('dw_end', 3)
    mode = st.session_state.get('papa_mode', '💼 Trabajando')

    def is_papas_shift(h):
        if dw_s > dw_e:
            if h >= dw_s or h < dw_e: return True
        else:
            if dw_s <= h < dw_e: return True
        
        if '🏠 Teletrabajo' in mode and 12 <= h < 14: return True
        if '🌴 Vacaciones' in mode and 8 <= h < 14: return True
        return False

    for _ in range(MAX_ITER):
        if cursor >= limit or len(agenda) >= 30:
            break

        h        = cursor.hour
        is_night = h >= 20 or h < 7

        if current_phase == "activity":
            if is_night:
                current_phase = "sleeping"
                sim_elapsed   = 0
                continue

            act_dur = max(5, aw_max - 15)
            wait    = max(1, act_dur - sim_elapsed)
            cursor += timedelta(minutes=wait)
            h       = cursor.hour
            on_duty = is_papas_shift(h)
            act_desc = ("Piel con piel, canto, móvil contrastes" if is_fase1 else "Tummy time, espejo, suelo")

            if on_duty:
                mama_ev = "💤 Descansando (Turno de papá)"
                papa_ev = f"🎯 {act_desc} · Vigila señales"
                bg, brd = "#EDE9FE", "#8B5CF6"
            else:
                mama_ev = f"🎯 {act_desc}"
                papa_ev = "💼 Trabajando" if 'Trabajando' in mode else "Otras tareas"
                bg, brd = "#FFF7ED", "#F97316"

            agenda.append(dict(
                hora=cursor.strftime("%H:%M"), icono="🎯",
                evento=f"Fin actividad → a dormir ({act_dur} min)",
                mama=mama_ev, papa=papa_ev, bg=bg, border=brd
            ))
            current_phase = "sleeping"
            sim_elapsed   = 0

        elif current_phase == "feeding":
            feed_dur = 25 if "materna" in feed_type.lower() else 20
            wait     = max(1, feed_dur - sim_elapsed)
            cursor  += timedelta(minutes=wait)
            h        = cursor.hour
            on_duty  = is_papas_shift(h)
            total_tomas += 1

            if on_duty:
                papa_role = papa_feed_method(days, feed_type)
                mama_role = "🤱 Da el pecho (semi-dormida)" if "materna" in feed_type.lower() and is_fase1 else "💤 DURMIENDO"
                bg, brd   = "#EFF6FF", "#3B82F6"
            else:
                papa_role = "💼 Trabajando" if 'Trabajando' in mode else "Acompaña / Tareas"
                mama_role = "🤱 Da el pecho / biberón"
                bg, brd   = "#F0FDF4", "#22C55E"

            agenda.append(dict(
                hora=cursor.strftime("%H:%M"), icono="🍼",
                evento=f"Toma #{total_tomas} terminada",
                mama=mama_role, papa=papa_role, bg=bg, border=brd
            ))
            current_phase = "sleeping" if is_night else "activity"
            sim_elapsed   = 0

        elif current_phase in ("sleeping", "idle"):
            sleep_dur, sleep_lbl = get_sleep_durations(days, is_night)
            wait          = max(1, sleep_dur - sim_elapsed)
            sleep_start   = cursor
            cursor       += timedelta(minutes=wait)
            wake_time_str = cursor.strftime("%H:%M")
            h             = cursor.hour
            on_duty       = is_papas_shift(sleep_start.hour)

            papa_hint = (papa_feed_method(days, feed_type) if "materna" not in feed_type.lower() else "jeringa/dedo/biberón según semanas")

            if on_duty:
                mama_role = "💤 DURMIENDO — bloque protegido"
                papa_role = (f"😴 DUERME AHORA — ⏰ pon alarma a las {wake_time_str} | Al sonar: {papa_hint}")
                bg, brd   = "#EDE9FE", "#8B5CF6"
            else:
                if not is_night:
                    mama_free_min += sleep_dur
                mama_role = "🛁 Ducha · Comida · Descanso"
                papa_role = "💼 Trabajando" if 'Trabajando' in mode else "Otras tareas"
                bg, brd   = "#ECFDF5", "#10B981"

            agenda.append(dict(
                hora=sleep_start.strftime("%H:%M"), icono="🌙",
                evento=f"Bebé se duerme — despertará ~{wake_time_str} ({sleep_lbl})",
                mama=mama_role, papa=papa_role, bg=bg, border=brd
            ))
            current_phase = "feeding"
            sim_elapsed   = 0

    dw_hours = (24 - dw_s + dw_e) if dw_s > dw_e else (dw_e - dw_s)
    
    papa_day_h = 0
    if '🏠 Teletrabajo' in mode: papa_day_h = 2.0
    elif '🌴 Vacaciones' in mode: papa_day_h = 6.0
    
    papa_total_duty_h = dw_hours + papa_day_h
    
    wh = st.session_state.get('work_hour', 7)
    papa_block_h = (24 - dw_e + wh) if dw_e > wh else (wh - dw_e)
    if papa_block_h < 0 or papa_block_h > 12: papa_block_h = 0

    summary = dict(
        tomas        = total_tomas,
        mama_sleep_h = float(dw_hours), 
        mama_free_h  = round(mama_free_min / 60, 1),
        papa_block_h = float(papa_block_h),
        papa_duty_h  = float(papa_total_duty_h),
    )
    return agenda, summary

def render_agenda(agenda, summary):
    if not agenda:
        st.info("Sin previsión disponible.")
        return

    st.markdown("#### 📊 Resumen proyectado (24h)")
    c1, c2, c3 = st.columns(3)
    c1.metric("🍼 Tomas mínimas", summary["tomas"])
    c2.metric("💤 Dream Window mamá", f"{summary['mama_sleep_h']}h")
    c3.metric("🌿 Tiempo libre mamá", f"{summary['mama_free_h']}h")

    c4, c5 = st.columns(2)
    c4.metric("🧔 Papá duerme del tirón", f"{summary['papa_block_h']}h")
    c5.metric("🕐 Guardia total papá", f"{summary['papa_duty_h']}h")

    st.markdown("---")

    prev_is_night = None
    for item in agenda:
        h          = int(item["hora"].split(":")[0])
        is_night   = h >= 20 or h < 7
        if prev_is_night is not None and is_night != prev_is_night:
            label = "🌙 Noche" if is_night else "☀️ Día"
            st.markdown(f"<div style='text-align:center;color:#6B7280;font-size:.8em;"
                        f"padding:6px 0;border-top:1px dashed #D1D5DB;'>{label}</div>",
                        unsafe_allow_html=True)
        prev_is_night = is_night

        st.markdown(f"""
        <div style='background:{item["bg"]};border-left:5px solid {item["border"]};
                    padding:12px;margin-bottom:8px;border-radius:8px;'>
            <div style='font-size:1.05em;color:#1F2937;margin-bottom:5px;'>
                <b>{item["hora"]}</b> &nbsp;{item["icono"]}&nbsp; <b>{item["evento"]}</b>
            </div>
            <div style='font-size:.88em;line-height:1.6;color:#374151;'>
                <b>👩 Mamá:</b> {item["mama"]}<br>
                <b>👨 Papá:</b> {item["papa"]}
            </div>
        </div>""", unsafe_allow_html=True)

# ─── VISTAS ───────────────────────────────────────────────────
DIAPER_TYPE_MAP = {
    "Pipí 💧":          "diaper_wet",
    "Caca 💩":          "diaper_dirty",
    "Pipí + Caca 💧💩": "diaper_both",
    "Seco 🏜️":          "diaper_dry",
}
DIAPER_ICONS = {"diaper_wet":"💧","diaper_dirty":"💩","diaper_both":"💧💩","diaper_dry":"🏜️"}
PHASE_ICONS  = {"feeding":"🍼","sleeping":"😴","activity":"🎯","idle":"☀️"}

def render_setup():
    st.markdown("<h1 style='text-align:center;'>🌙 BebéGuía</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#9CA3AF;'>Tu guía en equipo.</p>",
                unsafe_allow_html=True)
    with st.form("setup_form"):
        name  = st.text_input("Nombre del bebé")
        birth = st.date_input("Fecha de nacimiento (o fecha prevista de parto)",
                              value=datetime.date.today())
        feed  = st.selectbox("Alimentación", [
            "Lactancia materna exclusiva",
            "Mixta (pecho + biberón)",
            "Fórmula / Biberón",
        ])
        tz = st.number_input("Tu zona horaria (UTC+?)", value=1, min_value=-12, max_value=14, step=1,
                             help="Europa Central = 1 (invierno) o 2 (verano/CEST)")
        col_dw1, col_dw2 = st.columns(2)
        dw_start = col_dw1.number_input("Dream Window papá — empieza (hora)", value=21, min_value=18, max_value=23, step=1)
        dw_end   = col_dw2.number_input("Dream Window papá — termina (hora)", value=3, min_value=1, max_value=8, step=1)
        work_hour = st.number_input("Papá entra a trabajar a las (hora)", value=7, min_value=4, max_value=12, step=1)
        papa_mode = st.selectbox("Modo papá hoy", ["💼 Trabajando", "🏠 Teletrabajo", "🌴 Vacaciones"])
        
        if st.form_submit_button("Empezar →", use_container_width=True) and name:
            st.session_state.utc_offset = int(tz)
            st.session_state.dw_start   = int(dw_start)
            st.session_state.dw_end     = int(dw_end)
            st.session_state.work_hour  = int(work_hour)
            st.session_state.papa_mode  = papa_mode
            st.session_state.baby = {"name": name, "birth": birth, "feed": feed}
            st.session_state.page = "main"
            change_phase("idle")
            st.rerun()

def render_settings():
    st.subheader("⚙️ Configuración")
    baby = st.session_state.baby
    feed_opts = ["Lactancia materna exclusiva", "Mixta (pecho + biberón)", "Fórmula / Biberón"]
    with st.form("settings_form"):
        new_name  = st.text_input("Nombre", value=baby['name'])
        birth_val = baby.get('birth', datetime.date.today())
        if isinstance(birth_val, str):
            birth_val = datetime.datetime.strptime(birth_val, "%Y-%m-%d").date()
        new_birth = st.date_input("Fecha de nacimiento (o fecha prevista)", value=birth_val)
        idx      = feed_opts.index(baby['feed']) if baby['feed'] in feed_opts else 0
        new_feed = st.selectbox("Alimentación", feed_opts, index=idx)
        new_tz    = st.number_input("Zona horaria (UTC+?)",
                                   value=st.session_state.get('utc_offset', 1),
                                   min_value=-12, max_value=14, step=1)
        col_s1, col_s2 = st.columns(2)
        new_dw_start = col_s1.number_input("Dream Window papá — empieza",
                                            value=st.session_state.get('dw_start', 21),
                                            min_value=18, max_value=23, step=1)
        new_dw_end   = col_s2.number_input("Dream Window papá — termina",
                                            value=st.session_state.get('dw_end', 3),
                                            min_value=1, max_value=8, step=1)
        new_work     = st.number_input("Papá entra a trabajar a las",
                                       value=st.session_state.get('work_hour', 7),
                                       min_value=4, max_value=12, step=1)
        new_mode     = st.selectbox("Modo papá hoy",
                                    ["💼 Trabajando", "🏠 Teletrabajo", "🌴 Vacaciones"],
                                    index=["💼 Trabajando", "🏠 Teletrabajo", "🌴 Vacaciones"].index(
                                        st.session_state.get('papa_mode', '💼 Trabajando')))
        if st.form_submit_button("Guardar", use_container_width=True):
            st.session_state.baby.update(name=new_name, birth=new_birth, feed=new_feed)
            st.session_state.utc_offset = int(new_tz)
            st.session_state.dw_start   = int(new_dw_start)
            st.session_state.dw_end     = int(new_dw_end)
            st.session_state.work_hour  = int(new_work)
            st.session_state.papa_mode  = new_mode
            save_data()
            st.success("¡Guardado!")
            st.session_state.page = "main"
            st.rerun()
    if st.button("← Volver"):
        st.session_state.page = "main"; st.rerun()
    st.markdown("---")
    with st.expander("⚠️ Zona peligrosa"):
        if st.button("🗑️ Borrar todos los datos", type="primary"):
            try:
                sb = get_supabase()
                sb.table("bebe_state").delete().eq("id", RECORD_ID).execute()
            except Exception:
                pass
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

def render_main():
    baby   = st.session_state.baby
    days   = age_days()
    aw_max = get_aw_max(days)
    now    = now_local()
    el     = elapsed_min()

    c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 1, 1, 1])
    with c1:
        days_to_birth = (baby.get('birth', datetime.date.today()) - datetime.date.today()).days
        if isinstance(baby.get('birth'), str):
            birth_d = datetime.datetime.strptime(baby['birth'], "%Y-%m-%d").date()
            days_to_birth = (birth_d - datetime.date.today()).days
        if days > 0:
            age_str = f"{days}d · {days//7}sem"
        elif days_to_birth > 0:
            age_str = f"⏳ Nacerá en {days_to_birth} días"
        else:
            age_str = "Día 0 · ¡Bienvenido al mundo!"
        st.subheader(f"👶 {baby['name']}")
        st.caption(f"{age_str} · {baby['feed']}")
    with c2:
        if st.button("📖"): st.session_state.page = "guide";   st.rerun()
    with c3:
        if st.button("📊"): st.session_state.page = "metrics"; st.rerun()
    with c4:
        if st.button("📋"): st.session_state.page = "history"; st.rerun()
    with c5:
        if st.button("⚙️"): st.session_state.page = "settings"; st.rerun()
    with c6:
        if st.button("🔄", help="Sincronizar con el otro móvil"):
            db = load_data()
            if db:
                st.session_state.logs       = db.get('logs', [])
                st.session_state.phase      = db.get('phase', st.session_state.phase)
                st.session_state.phaseStart = db.get('phaseStart', st.session_state.phaseStart)
                st.session_state.timer_paused   = db.get('timer_paused', False)
                st.session_state.paused_seconds = db.get('paused_seconds', 0)
                st.session_state.pause_start    = db.get('pause_start')
            st.rerun()

    st.markdown("---")
    phase = st.session_state.phase

    # ── BANNER: último evento completado y su valoración ──────────
    lc = st.session_state.get('last_completed')
    if lc and lc.get('msg'):
        icon_map = {"feeding": "🍼", "sleeping": "😴", "activity": "🎯"}
        tipo_txt = {"feeding": "Toma", "sleeping": "Sueño", "activity": "Actividad"}
        st.markdown(
            f"<div style='background:{lc['bg']};border-left:5px solid {lc['border']};"
            f"padding:12px 14px;border-radius:8px;margin-bottom:12px;'>"
            f"<div style='font-size:0.8em;color:#6B7280;margin-bottom:2px;'>"
            f"✔ Registrado · {icon_map.get(lc['type'],'')} {tipo_txt.get(lc['type'],lc['type'])} "
            f"· desde las {lc['hora']} · <b>{lc['dur']} min</b> · rango esperado: {lc['rango']}</div>"
            f"<div style='font-size:0.93em;color:#1F2937;'>{lc['emoji']} {lc['msg']}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    # --- CRONÓMETRO EN VIVO CON PAUSA ---
    if phase != "idle" and st.session_state.phaseStart:
        diff_sec  = elapsed_sec()
        is_paused = st.session_state.get('timer_paused', False)

        if phase == "sleeping":
            t_color = "#8B5CF6"
            t_icon, t_label = "😴", "Durmiendo"
        elif phase == "feeding":
            t_color = "#22C55E"
            t_icon, t_label = "🍼", "Comiendo"
        else:
            t_color = "#F97316"
            t_icon, t_label = "🎯", "Actividad"

        pause_bg = "#FEF3C7" if is_paused else "#f9fafb"
        pause_border = "#F59E0B" if is_paused else "#e5e7eb"
        paused_notice = "<div style='font-size:0.85rem;color:#B45309;font-weight:bold;margin-top:4px;'>⏸ PAUSADO</div>" if is_paused else ""

        html_timer = f"""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                    padding:10px;background:{pause_bg};border-radius:12px;
                    border:1px solid {pause_border};margin-bottom:15px;">
            <div style="font-size:1.1rem;color:#4B5563;font-weight:bold;font-family:system-ui,sans-serif;">
                {t_icon} {t_label}
            </div>
            <div id="live-timer" style="font-size:4rem;font-weight:900;color:{t_color};
                 font-variant-numeric:tabular-nums;line-height:1.1;font-family:system-ui,sans-serif;">
                00:00
            </div>
            {paused_notice}
        </div>
        <script>
            var diff    = {diff_sec};
            var running = {"false" if is_paused else "true"};
            var el      = document.getElementById("live-timer");
            function fmt() {{
                var h = Math.floor(diff/3600);
                var m = Math.floor((diff%3600)/60);
                var s = diff%60;
                var t = (m<10?"0"+m:m)+":"+(s<10?"0"+s:s);
                if (h>0) t = h+":"+t;
                el.innerHTML = t;
            }}
            fmt();
            setInterval(function(){{if(running){{diff++;fmt();}}}}, 1000);
        </script>
        """
        components.html(html_timer, height=145)

        # Botón de pausa / reanudar
        pause_label = "▶️ Reanudar" if is_paused else "⏸ Pausar"
        if st.button(pause_label, key="btn_pause", use_container_width=False):
            if is_paused:
                # Reanudar: acumular los segundos pausados y limpiar pause_start
                if st.session_state.pause_start:
                    st.session_state.paused_seconds += int(
                        (now_local() - st.session_state.pause_start).total_seconds()
                    )
                st.session_state.pause_start  = None
                st.session_state.timer_paused = False
            else:
                # Pausar
                st.session_state.pause_start  = now_local()
                st.session_state.timer_paused = True
            save_data()
            st.rerun()
    
    # --- MENSAJES DINÁMICOS DE ESTADO CON RANGOS ─────────────────
    if phase == "idle":
        st.info("☀️ **Despierto y tranquilo** — Ofrécele pecho/biberón cuando busque.")

    elif phase == "feeding":
        lo, hi = get_feed_range(days)
        if el < lo:
            pct = int(el / lo * 100)
            st.info(f"🍼 Toma en curso · {el} min — Rango esperado: **{lo}–{hi} min** "
                    f"· Quedan al menos **{lo - el} min** para completar el mínimo.")
        elif el <= hi:
            st.success(f"🍼 Toma en curso · {el} min ✅ — Dentro del rango ({lo}–{hi} min). "
                       f"{'Si se duerme comiendo: normal antes de los 4 meses, ponlo a dormir directamente.' if days < 120 else 'Intenta que termine despierto.'}")
        else:
            st.warning(f"🍼 Toma larga · {el} min ⚠️ — El rango esperado es {lo}–{hi} min. "
                       f"¿Está usando el pecho de chupete? Puedes valorar terminar la toma.")

    elif phase == "sleeping":
        h = now.hour
        is_night = h >= 20 or h < 7
        lo_s, hi_s, lbl_s = get_sleep_range(days, is_night)
        tipo_s = "nocturno" if is_night else "diurno"
        st.markdown("<div style='text-align:center;color:#6B7280;font-size:0.9em;margin-bottom:10px;'>Boca arriba · superficie firme · sin mantas sueltas.</div>", unsafe_allow_html=True)
        if el < lo_s:
            st.info(f"😴 Sueño {tipo_s} · {el} min — Rango esperado: **{lbl_s}** · Aún dentro del ciclo normal.")
        elif el <= hi_s:
            st.success(f"😴 Sueño {tipo_s} · {el} min ✅ — Dentro del rango esperado ({lbl_s}).")
        else:
            if is_night:
                st.success(f"🌙 Sueño nocturno largo · {el} min 🎉 — ¡Muy bien! Rango base era {lbl_s}.")
            else:
                st.warning(f"⚠️ Siesta muy larga · {el} min — Rango diurno: {lbl_s}. "
                           f"Considera despertarlo para proteger el sueño nocturno.")
        if days < 30 and el >= 210:
            st.error("🚨 Casi 4h sin comer. Despiértalo suavemente.")

    elif phase == "activity":
        lo_a, hi_a = get_aw_range(days)
        pct   = min(int(el / hi_a * 100), 100)
        color = "#22C55E" if pct < 60 else ("#F97316" if pct < 85 else "#EF4444")
        st.markdown(
            f"<div style='background:#E5E7EB;border-radius:8px;height:14px;margin-bottom:8px;'>"
            f"<div style='background:{color};width:{pct}%;height:14px;border-radius:8px;"
            f"transition:width 0.3s;'></div></div>",
            unsafe_allow_html=True)
        if el < lo_a:
            st.info(f"🎯 Actividad · {el} min — Ventana: **{lo_a}–{hi_a} min** · Aún en la primera mitad, bien.")
        elif el <= hi_a:
            quedan = hi_a - el
            msg = f"🎯 Actividad · {el} min ✅ — Rango: {lo_a}–{hi_a} min · Quedan ~{quedan} min de ventana."
            if pct >= 80:
                st.warning(f"⏰ {msg} Empieza a calmarlo pronto.")
            else:
                st.info(msg)
        else:
            st.error(f"🚨 Ventana cerrada · {el} min (máx {hi_a} min). Señales de cansancio: bostezo, mirada perdida, puños cerrados. Acuéstalo ya.")

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("🍼 Comer",  use_container_width=True): change_phase("feeding");  st.rerun()
    if c2.button("😴 Dormir", use_container_width=True): change_phase("sleeping"); st.rerun()
    if c3.button("🎯 Jugar",  use_container_width=True): change_phase("activity"); st.rerun()
    if c4.button("🧷 Pañal",  use_container_width=True): st.session_state.page = "diaper"; st.rerun()
    if c5.button("📝 Olvidé", use_container_width=True): st.session_state.page = "log_past"; st.rerun()

    st.markdown("---")
    hoy = now.date()
    logs_hoy = [l for l in st.session_state.logs if l['ts'].date() == hoy]
    tomas = sum(1 for l in logs_hoy if l['type'] == "feeding")
    wet   = sum(1 for l in logs_hoy if l['type'] in ("diaper_wet", "diaper_both"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Tomas hoy", tomas, help="Meta orientativa: ≥8/día")
    col2.metric("Pañales mojados", wet, help="Mínimo: 6/día")
    col3.metric("Tiempo en fase", f"{el} min")

    st.markdown("---")
    st.subheader("📅 Planificador EASY — Próximas 24h")
    st.caption("Se ajusta al ritmo real del bebé. Morado = turno de papá (Dream Window).")
    agenda, summary = build_agenda(baby, now, phase, el)
    render_agenda(agenda, summary)

def render_history():
    st.subheader("📋 Historial de hoy")
    if st.button("← Volver"): st.session_state.page = "main"; st.rerun()
    hoy = now_local().date()
    days = age_days()
    logs_hoy_idx = [(i, l) for i, l in enumerate(st.session_state.logs)
                    if l['ts'].date() == hoy]
    if not logs_hoy_idx:
        st.info("Sin registros hoy.")
    else:
        st.caption("Toca 🗑️ para borrar un registro incorrecto.")
        type_label = {"feeding": "Toma", "sleeping": "Sueño", "activity": "Actividad",
                      "diaper_wet": "Pañal mojado", "diaper_dirty": "Pañal caca",
                      "diaper_both": "Pañal completo", "diaper_dry": "Pañal seco"}
        for global_i, l in reversed(logs_hoy_idx):
            hora  = l['ts'].strftime("%H:%M")
            icono = DIAPER_ICONS.get(l['type'], PHASE_ICONS.get(l['type'], "📝"))
            dur   = l.get('durMin', 0)
            col_s = l.get('color', '')
            label = type_label.get(l['type'], l['type'])

            # Valoración de duración
            emoji_v, bg_v, border_v, msg_v, rango_v = assess_log(l['type'], dur, l['ts'], days)

            # Construir tarjeta
            if msg_v:
                bg_card = bg_v; border_card = border_v
                dur_txt = f"{dur} min &nbsp;·&nbsp; <span style='font-size:0.8em;color:#6B7280;'>esperado: {rango_v}</span>"
                assess_html = f"<div style='font-size:0.82em;color:#374151;margin-top:3px;'>{emoji_v} {msg_v}</div>"
            else:
                bg_card = "#F9FAFB"; border_card = "#D1D5DB"
                dur_txt = ""
                assess_html = f"<div style='font-size:0.82em;color:#6B7280;'>{col_s}</div>" if col_s else ""

            c_txt, c_btn = st.columns([6, 1])
            with c_txt:
                st.markdown(
                    f"<div style='background:{bg_card};border-left:4px solid {border_card};"
                    f"padding:8px 12px;border-radius:6px;margin-bottom:6px;'>"
                    f"<div style='font-size:0.95em;color:#111827;'>"
                    f"<b>{hora}</b> &nbsp; {icono} <b>{label}</b>"
                    + (f" &nbsp;·&nbsp; {dur_txt}" if dur else "") +
                    f"</div>"
                    f"{assess_html}"
                    f"</div>",
                    unsafe_allow_html=True
                )
            if c_btn.button("🗑️", key=f"del_{global_i}"):
                st.session_state.logs.pop(global_i)
                save_data()
                st.rerun()
    st.markdown("---")
    lines = ["hora,tipo,duracion_min,color"]
    for _, l in logs_hoy_idx:
        lines.append(f"{l['ts'].strftime('%H:%M')},{l['type']},"
                     f"{l.get('durMin','')},{l.get('color','')}")
    st.download_button("⬇️ Exportar CSV", "\n".join(lines),
                       file_name=f"bebe_{hoy}.csv", mime="text/csv")

def render_diaper():
    st.subheader("🧷 ¿Qué hay en el pañal?")
    tipo_label = st.radio("Contenido:", list(DIAPER_TYPE_MAP.keys()))
    color = None
    if "Caca" in tipo_label:
        color = st.selectbox("Color:", [
            "Mostaza 🟡 (Normal)",
            "Verde 💚 (Normal/Transición)",
            "Meconio ⬛ (Normal primeros días)",
            "Blanca/Gris ⬜ (⚠️ Alerta pediátrica)",
            "Roja/Sangre 🔴 (⚠️ Alerta pediátrica)",
        ])
    c1, c2 = st.columns(2)
    if c1.button("Guardar", type="primary"):
        add_log(DIAPER_TYPE_MAP[tipo_label], color=color)
        if color and ("Blanca" in color or "Roja" in color):
            st.error("⚠️ Este color requiere valoración pediátrica.")
        else:
            st.session_state.page = "main"; st.rerun()
    if c2.button("Cancelar"):
        st.session_state.page = "main"; st.rerun()

def render_log_past():
    """Permite registrar un evento pasado que se olvidó anotar en tiempo real."""
    st.subheader("📝 Registrar evento olvidado")
    st.caption("Añade una toma, siesta o actividad que ocurrió antes y no registraste.")

    if st.button("← Volver"): st.session_state.page = "main"; st.rerun()

    now   = now_local()
    today = now.date()

    tipo_display = st.selectbox(
        "¿Qué ocurrió?",
        ["🍼 Toma (alimentación)", "😴 Siesta / sueño", "🎯 Actividad / juego",
         "💧 Pañal pipí", "💩 Pañal caca", "💧💩 Pañal pipí + caca"]
    )
    tipo_map = {
        "🍼 Toma (alimentación)": "feeding",
        "😴 Siesta / sueño":      "sleeping",
        "🎯 Actividad / juego":   "activity",
        "💧 Pañal pipí":          "diaper_wet",
        "💩 Pañal caca":          "diaper_dirty",
        "💧💩 Pañal pipí + caca": "diaper_both",
    }
    tipo = tipo_map[tipo_display]

    st.markdown("**¿Cuándo empezó?**")
    col_h, col_m = st.columns(2)
    hora_h = col_h.number_input("Hora", min_value=0, max_value=23, value=now.hour, step=1)
    hora_m = col_m.number_input("Minuto", min_value=0, max_value=59, value=max(0, now.minute - 5), step=5)

    # Determinar si es hoy o ayer (si la hora futura → asumir ayer)
    ts_candidate = datetime.datetime.combine(today, datetime.time(int(hora_h), int(hora_m)))
    ts_candidate = ts_candidate.replace(tzinfo=None)  # sin tz, igual que now_local()
    if ts_candidate > now:
        ts_candidate -= datetime.timedelta(days=1)

    dur_min = 0
    if tipo in ("feeding", "sleeping", "activity"):
        dur_min = st.number_input(
            "Duración (minutos)",
            min_value=1, max_value=480,
            value=20 if tipo == "feeding" else (90 if tipo == "sleeping" else 30),
            step=5
        )

    color = None
    if tipo == "diaper_dirty":
        color = st.selectbox("Color de la caca:", [
            "Mostaza 🟡 (Normal)", "Verde 💚 (Normal/Transición)",
            "Meconio ⬛ (Normal primeros días)",
            "Blanca/Gris ⬜ (⚠️ Alerta pediátrica)",
            "Roja/Sangre 🔴 (⚠️ Alerta pediátrica)",
        ])

    # Opción de actualizar la fase actual
    ts_fin = ts_candidate + datetime.timedelta(minutes=int(dur_min))
    actualizar_fase = False
    if tipo in ("feeding", "sleeping", "activity") and ts_fin <= now:
        fase_sugerida = {
            "feeding": "sleeping" if (now_local().hour >= 20 or now_local().hour < 7) else "activity",
            "sleeping": "feeding",
            "activity": "sleeping",
        }.get(tipo, "idle")
        actualizar_fase = st.checkbox(
            f"Actualizar fase actual → el bebé empezó a "
            f"{'🍼 comer' if fase_sugerida=='feeding' else '😴 dormir' if fase_sugerida=='sleeping' else '🎯 jugar'}"
            f" a las {ts_fin.strftime('%H:%M')} (justo después de este evento)",
            value=True
        )

    st.caption(f"📅 Se registrará como: **{ts_candidate.strftime('%H:%M')}** del "
               f"{'hoy' if ts_candidate.date() == today else 'ayer'}"
               + (f" · duración: **{dur_min} min** · fin: **{ts_fin.strftime('%H:%M')}**"
                  if dur_min else ""))

    col_ok, col_cancel = st.columns(2)
    if col_ok.button("✅ Guardar evento", type="primary"):
        add_log(tipo, dur_min=int(dur_min), color=color, ts=ts_candidate)
        if actualizar_fase and tipo in ("feeding", "sleeping", "activity"):
            st.session_state.phase          = fase_sugerida
            st.session_state.phaseStart     = ts_fin
            st.session_state.timer_paused   = False
            st.session_state.paused_seconds = 0
            st.session_state.pause_start    = None
            save_data()
        st.success("✅ Evento guardado. El pronóstico se actualizará.")
        st.session_state.page = "main"
        st.rerun()
    if col_cancel.button("Cancelar"):
        st.session_state.page = "main"; st.rerun()


def render_metrics():
    st.subheader("📊 Métricas del día")
    if st.button("← Volver"): st.session_state.page = "main"; st.rerun()

    now = now_local()
    hoy = now.date()
    logs_hoy = [l for l in st.session_state.logs if l['ts'].date() == hoy]
    days = age_days()

    if not logs_hoy and st.session_state.phase == "idle":
        st.info("Sin datos de hoy todavía. Empieza a registrar con los botones.")
        return

    sleep_logs = [l for l in logs_hoy if l['type'] == 'sleeping']
    feed_logs  = [l for l in logs_hoy if l['type'] == 'feeding']
    wet_logs   = [l for l in logs_hoy if l['type'] in ('diaper_wet', 'diaper_both')]
    dirty_logs = [l for l in logs_hoy if l['type'] in ('diaper_dirty', 'diaper_both')]

    total_sleep_min = sum(l.get('durMin', 0) for l in sleep_logs)
    current_el = elapsed_min()
    if st.session_state.phase == 'sleeping':
        total_sleep_min += current_el
    longest_sleep = max((l.get('durMin', 0) for l in sleep_logs), default=0)
    if st.session_state.phase == 'sleeping':
        longest_sleep = max(longest_sleep, current_el)

    mins_since_midnight = int((now - datetime.datetime.combine(hoy, datetime.time.min)).total_seconds() / 60)
    pct_sleep = round(total_sleep_min / mins_since_midnight * 100) if mins_since_midnight > 0 else 0
    sleep_ok = pct_sleep >= 55

    total_feed_min = sum(l.get('durMin', 0) for l in feed_logs)
    avg_feed = round(total_feed_min / len(feed_logs)) if feed_logs else 0
    feed_times = sorted([l['ts'] for l in feed_logs])
    if len(feed_times) >= 2:
        intervals = [(feed_times[i+1]-feed_times[i]).total_seconds()/60
                     for i in range(len(feed_times)-1)]
        avg_interval = round(sum(intervals)/len(intervals))
    else:
        avg_interval = None
    last_feed = max((l['ts'] for l in feed_logs), default=None)
    min_since_feed = int((now - last_feed).total_seconds()/60) if last_feed else None

    st.markdown("---")
    st.markdown("#### 😴 Sueño")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total dormido hoy",
              f"{total_sleep_min//60}h {total_sleep_min%60}m",
              help="RN: 16–18h/día es normal")
    c2.metric("Tramo más largo", f"{longest_sleep} min",
              help="Con el tiempo este número irá creciendo")
    ok_txt = "✅ Bien" if sleep_ok else "⚠️ Poco"
    c3.metric("% día dormido", f"{pct_sleep}%", delta=ok_txt,
              help="Referencia RN: ≥65% del día")

    st.markdown("#### 🍼 Alimentación")
    c4, c5, c6 = st.columns(3)
    c4.metric("Tomas completadas", len(feed_logs),
              delta="✅ Bien" if len(feed_logs) >= 8 else "⚠️ Meta: 8",
              help="Meta orientativa: ≥8 tomas/día en primeras semanas")
    c5.metric("Duración media", f"{avg_feed} min" if avg_feed else "–",
              help="Normal: 10–25 min por toma")
    c6.metric("Intervalo medio entre tomas",
              f"{avg_interval} min" if avg_interval else "–",
              help="Recomendado <180 min en primeras 3 semanas")

    if min_since_feed is not None:
        alerta = days < 21 and min_since_feed > 180
        msg = (f"🔴 **Última toma hace {min_since_feed} min** — ¡Hay que alimentar!"
               if alerta else
               f"🟢 Última toma hace **{min_since_feed} min**")
        st.info(msg)

    st.markdown("#### 🧷 Pañales")
    c7, c8, c9 = st.columns(3)
    wet_ok = len(wet_logs) >= 6
    c7.metric("Mojados 💧", len(wet_logs),
              delta="✅ Bien" if wet_ok else "⚠️ Meta: 6",
              help="≥6 pañales mojados/día = buena hidratación")
    c8.metric("Con caca 💩", len(dirty_logs),
              help="Variable según edad y método de alimentación")
    total_diapers = len([l for l in logs_hoy if l['type'].startswith('diaper')])
    c9.metric("Total pañales", total_diapers)

    st.markdown("#### 📈 Línea de tiempo de hoy")
    if logs_hoy:
        icons_map = {"feeding":"🍼","sleeping":"😴","activity":"🎯",
                     "idle":"☀️","diaper_wet":"💧","diaper_dirty":"💩",
                     "diaper_both":"💧💩","diaper_dry":"🏜️"}
        events = sorted(logs_hoy, key=lambda x: x['ts'])
        timeline = "  →  ".join(
            f"{l['ts'].strftime('%H:%M')} {icons_map.get(l['type'],'📝')}"
            for l in events
        )
        st.markdown(f"<div style='font-size:0.85em;color:#374151;line-height:2;'>{timeline}</div>",
                    unsafe_allow_html=True)
    else:
        st.caption("Sin eventos registrados aún.")

def render_guide():
    st.subheader("📖 Guía de desarrollo")
    if st.button("← Volver"): st.session_state.page = "main"; st.rerun()

    days  = age_days()
    weeks = days // 7
    feed  = (st.session_state.baby or {}).get('feed', 'Lactancia materna exclusiva')

    max_w = max(weeks, 0)
    sel_w = st.slider("Ver guía para la semana:", 0, 24, max_w,
                      help="Mueve para explorar cómo evolucionará el bebé")
    sel_days = sel_w * 7

    if sel_w < 4:
        etapa = "🌱 Recién nacido (0–4 semanas)"; color = "#FEF9C3"
    elif sel_w < 8:
        etapa = "🌿 Primer mes (4–8 semanas)"; color = "#DCFCE7"
    elif sel_w < 12:
        etapa = "🌸 Segundo mes (8–12 semanas)"; color = "#E0F2FE"
    elif sel_w < 24:
        etapa = "🌻 3–6 meses (12–24 semanas)"; color = "#EDE9FE"
    else:
        etapa = "🌳 +6 meses"; color = "#FEE2E2"

    st.markdown(f"<div style='background:{color};padding:10px 14px;"
                f"border-radius:8px;font-weight:bold;margin-bottom:16px;'>"
                f"{etapa} — Semana {sel_w}</div>", unsafe_allow_html=True)

    st.markdown("### 😴 Sueño")
    aw_lo, aw_hi = get_aw_range(sel_days)
    lo_n, hi_n, lbl_n = get_sleep_range(sel_days, is_night=True)
    lo_d, hi_d, lbl_d = get_sleep_range(sel_days, is_night=False)

    if sel_w < 4:
        total_h = "16–20h"; notas_sueno = "No hay ritmo circadiano. Día = Noche para él. Normal despertar cada 2–3h."
    elif sel_w < 8:
        total_h = "15–17h"; notas_sueno = "Empieza a agrupar ligeramente por las noches. Aún normal despertar 2–3× noche."
    elif sel_w < 12:
        total_h = "~15h"; notas_sueno = "Inicia producción de melatonina. Empieza a distinguir día/noche."
    elif sel_w < 24:
        total_h = "12–16h"; notas_sueno = "Posible regresión de los 4 meses (cambio de ciclos de sueño). Normal y temporal."
    else:
        total_h = "12–14h"; notas_sueno = "Ciclos de sueño más parecidos al adulto."

    c1, c2, c3 = st.columns(3)
    c1.metric("Total/día", total_h)
    c2.metric("Bloque nocturno", lbl_n)
    c3.metric("Siesta diurna", lbl_d)
    st.caption(f"⏱️ Ventana de vigilia: **{aw_lo}–{aw_hi} min** despierto antes de la próxima siesta")
    st.info(f"💡 {notas_sueno}")

    st.markdown("### 🍼 Alimentación")
    is_breast = "materna" in feed.lower()

    if sel_w < 1:
        tomas_dia = "8–12"; ml_toma = "5–10 ml (calostro)"; intervalo = "cada 1–3h"
        nota_ali = "Estómago tamaño canica. El calostro es suficiente y perfecto. No suplementar sin indicación."
    elif sel_w < 2:
        tomas_dia = "8–12"; ml_toma = "20–60 ml"; intervalo = "cada 2–3h"
        nota_ali = "Sube la leche madura (días 3–5). Tomas muy frecuentes = estimulación de producción."
    elif sel_w < 4:
        tomas_dia = "8–10"; ml_toma = "60–90 ml"; intervalo = "cada 2–3h"
        nota_ali = "Si vacía el pecho/biberón y parece insatisfecho → sube 20–30 ml la próxima toma."
    elif sel_w < 8:
        tomas_dia = "7–9"; ml_toma = "90–120 ml"; intervalo = "cada 2.5–3.5h"
        nota_ali = "Tomas más espaciadas y eficientes. Normal que alguna dure solo 5–10 min."
    elif sel_w < 12:
        tomas_dia = "6–8"; ml_toma = "120–150 ml"; intervalo = "cada 3–4h"
        nota_ali = "Más despierto e interesado en el entorno. Puede distraerse durante la toma."
    elif sel_w < 24:
        tomas_dia = "5–7"; ml_toma = "150–180 ml"; intervalo = "cada 3.5–4.5h"
        nota_ali = "A los 6 meses se introduce alimentación complementaria. La leche sigue siendo principal."
    else:
        tomas_dia = "4–5"; ml_toma = "180–240 ml"; intervalo = "cada 4–5h"
        nota_ali = "Papillas y purés como complemento. Nunca en sustitución de la leche antes del año."

    c4, c5, c6 = st.columns(3)
    c4.metric("Tomas/día", tomas_dia)
    c5.metric("Cantidad/toma", ml_toma if not is_breast else "A demanda")
    c6.metric("Intervalo", intervalo)

    if is_breast:
        papa_metodo = papa_feed_method(sel_days, feed)
        st.success(f"👨 **Papá puede alimentar:** {papa_metodo}")
    st.info(f"💡 {nota_ali}")

    st.markdown("### 💩 Deposiciones")
    if sel_w < 1:
        dep_frec = "3–4/día (puede llegar a 8–10)"; dep_color = "Negro/verde oscuro (meconio)"
        dep_nota = "El meconio es normal. Debe desaparecer en 48–72h. Cuenta los pañales para valorar ingesta."
    elif sel_w < 2:
        dep_frec = "3–6/día"; dep_color = "Verde transición → mostaza"
        dep_nota = "Cambio de color = la leche madura está llegando. Buena señal."
    elif sel_w < 8:
        if is_breast:
            dep_frec = "1–8/día (muy variable)"; dep_color = "Mostaza, granulada, líquida"
            dep_nota = "Con lactancia materna es completamente normal no hacer caca varios días."
        else:
            dep_frec = "1–3/día"; dep_color = "Amarillo-marrón, más consistente"
            dep_nota = "Con fórmula son más consistentes y menos frecuentes. ≥1/día es normal."
    elif sel_w < 24:
        dep_frec = "1–4/día o cada 2–3 días"; dep_color = "Amarillo/marrón"
        dep_nota = "La frecuencia se regula con la edad. Lo importante es que sean blandas, no duras."
    else:
        dep_frec = "1–2/día"; dep_color = "Marrón, más adulta"
        dep_nota = "Con la alimentación complementaria el color y consistencia cambiarán según lo que coma."

    c7, c8 = st.columns(2)
    c7.metric("Frecuencia esperada", dep_frec)
    c8.metric("Color normal", dep_color)
    st.info(f"💡 {dep_nota}")
    st.error("🚨 **Consultar al pediatra si:** color blanco/gris/rojo, sangre visible, sin deposición + llanto intenso + abdomen duro.")

    st.markdown("### ⚖️ Peso y crecimiento")
    st.caption("Introduce el peso de nacimiento para calcular la curva esperada.")
    peso_nac = st.number_input("Peso al nacer (gramos)", value=3300, step=50,
                                min_value=1500, max_value=5000)
    if sel_w == 0:
        peso_esp = peso_nac; nota_peso = "Peso de referencia."
    elif sel_w <= 2:
        perdida = peso_nac * 0.07
        recuperacion = perdida / 2 * sel_w
        peso_esp = int(peso_nac - perdida + recuperacion)
        nota_peso = "Pérdida fisiológica normal hasta 10%. Recupera peso nacimiento ~2 semanas."
    elif sel_w <= 12:
        peso_esp = int(peso_nac + (sel_w - 2) * 180)
        nota_peso = "Ganancia esperada: 150–200g/semana en el primer trimestre."
    elif sel_w <= 24:
        base = peso_nac + 10 * 180
        peso_esp = int(base + (sel_w - 12) * 120)
        nota_peso = "Ganancia esperada: 100–130g/semana en el segundo trimestre."
    else:
        base = peso_nac + 10 * 180 + 12 * 120
        peso_esp = int(base + (sel_w - 24) * 80)
        nota_peso = "Ganancia esperada: ~70–90g/semana."

    c9, c10 = st.columns(2)
    c9.metric(f"Peso esperado semana {sel_w}",
              f"{peso_esp:,} g  ({round(peso_esp/1000,2)} kg)")
    c10.metric("Vs. nacimiento", f"{peso_esp - peso_nac:+,} g")
    st.info(f"💡 {nota_peso}")
    st.caption("⚠️ Estos valores son orientativos. El pediatra valorará la curva individual con percentiles.")

    st.markdown("### 🧠 Desarrollo esperado")
    if sel_w < 4:
        hitos = ["Fija la mirada a 20–30 cm", "Reflejo de búsqueda y succión",
                 "Responde a sonidos fuertes", "Mueve brazos y piernas simétricamente"]
        alertas = ["No responde a la voz", "No fija la mirada en ningún momento",
                   "Llanto muy agudo o ausente"]
    elif sel_w < 8:
        hitos = ["Sonrisa social (semana 6–8)", "Sigue objetos con los ojos",
                 "Vocaliza pequeños sonidos", "Levanta ligeramente la cabeza boca abajo"]
        alertas = ["Sin sonrisa social a los 2 meses", "No sigue objetos con la vista"]
    elif sel_w < 12:
        hitos = ["Ríe en voz alta", "Sigue objetos 180°", "Sostiene la cabeza mejor",
                 "Manotea objetos", "Reconoce caras familiares"]
        alertas = ["Sin vocalización", "No sostiene la cabeza en absoluto a las 12 semanas"]
    elif sel_w < 24:
        hitos = ["Se da la vuelta (4–5 meses)", "Agarra objetos", "Balbucea (ba, ma, da)",
                 "Se sienta con apoyo", "Reconoce su nombre"]
        alertas = ["Sin balbuceo a los 6 meses", "No intenta alcanzar objetos",
                   "No aguanta peso en las piernas al sostenerlo de pie"]
    else:
        hitos = ["Se sienta solo", "Pinza índice-pulgar", "Imita gestos",
                 "Gatea o intenta moverse", "Primeras palabras ~12 meses"]
        alertas = ["Sin movilidad dirigida", "Sin gestos imitativos", "Sin palabras a los 12 meses"]

    c11, c12 = st.columns(2)
    with c11:
        st.markdown("**✅ Hitos esperados:**")
        for h in hitos:
            st.markdown(f"- {h}")
    with c12:
        st.markdown("**🚨 Consultar si:**")
        for a in alertas:
            st.markdown(f"- {a}")

    st.markdown("### 🤗 Contacto y porteo")
    if sel_w < 8:
        st.success("Piel con piel ilimitado — regula temperatura, glucemia, frecuencia cardiaca y favorece la lactancia. "
                   "El porteo fisiológico desde el nacimiento es seguro y reduce el llanto hasta un 43%.")
    elif sel_w < 16:
        st.success("Porteo fisiológico recomendado. Posición en M, espalda redondeada, cara visible. "
                   "El contacto sigue siendo esencial para el desarrollo neurológico.")
    else:
        st.info("Sigue siendo beneficioso. A esta edad le interesa más explorar el entorno. "
                "Alterna porteo con tiempo en el suelo para favorecer el desarrollo motor.")

    st.markdown("---")
    st.caption("Fuentes: OMS, AAP, ESPGHAN, Sears (The Baby Book), Gonzalez (Un regalo para toda la vida)")


# ─── ROUTER ───────────────────────────────────────────────────
{
    "setup":    render_setup,
    "settings": render_settings,
    "main":     render_main,
    "diaper":   render_diaper,
    "history":  render_history,
    "metrics":  render_metrics,
    "guide":    render_guide,
    "log_past": render_log_past,
}.get(st.session_state.page, render_setup)()
