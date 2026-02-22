# 🚀 Guía de despliegue — BebéGuía en la nube
# Para que tú y María podáis usar la app desde vuestros móviles, sincronizados

## Qué necesitas (todo gratis)
- Cuenta en GitHub: https://github.com
- Cuenta en Supabase: https://supabase.com
- Cuenta en Streamlit Cloud: https://share.streamlit.io

---

## PASO 1 — Crear la base de datos en Supabase

1. Entra en https://supabase.com → "Start your project"
2. Crea un nuevo proyecto (nombre: bebaeguia, región: Europe West)
3. Espera ~2 min a que se inicialice
4. Ve a **SQL Editor** (menú izquierdo) y ejecuta este SQL:

```sql
CREATE TABLE bebe_state (
  id    INTEGER PRIMARY KEY,
  state JSONB NOT NULL DEFAULT '{}'
);
INSERT INTO bebe_state (id, state) VALUES (1, '{}');
```

5. Ve a **Project Settings → API**
   - Copia la **Project URL** → la necesitarás (ej: https://abcdef.supabase.co)
   - Copia la **anon public key** → la necesitarás (empieza con eyJ...)

---

## PASO 2 — Subir el código a GitHub

1. Crea un nuevo repositorio en GitHub (privado recomendado)
2. Sube estos archivos:
   - `app.py`          ← renombra bebe_guia_cloud.py a app.py
   - `requirements.txt`
3. NO subas secrets.toml ni bebe_db.json

---

## PASO 3 — Desplegar en Streamlit Cloud

1. Entra en https://share.streamlit.io
2. Conecta tu cuenta de GitHub
3. "New app" → selecciona tu repositorio → Main file path: `app.py`
4. Antes de hacer Deploy, ve a **Advanced settings → Secrets** y añade:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR..."
```

5. Deploy → en 1-2 min tendrás una URL pública como:
   `https://bebaeguia-tuusuario.streamlit.app`

---

## PASO 4 — Instalar en el móvil como app

**En iPhone (Safari):**
1. Abre la URL en Safari
2. Botón Compartir → "Añadir a pantalla de inicio"
3. Se instala como si fuera una app nativa

**En Android (Chrome):**
1. Abre la URL en Chrome
2. Menú ⋮ → "Añadir a pantalla de inicio"

---

## 🔄 Sincronización entre móviles

- Cada vez que uno de los dos registra un evento, se guarda en Supabase
- El otro puede pulsar el botón **🔄** (esquina superior derecha) para sincronizar
- Streamlit refresca la página automáticamente al hacer cualquier acción
- Para sincronización en tiempo real sin tocar nada, simplemente recarga la página

---

## ❓ Preguntas frecuentes

**¿Es seguro?**
Sí. Supabase cifra los datos. La anon key solo permite leer/escribir la tabla específica.
Usa un repositorio privado en GitHub para que el código no sea público.

**¿Tiene coste?**
No. Streamlit Cloud (gratis hasta 1GB/app), Supabase (gratis hasta 500MB).
Para un bebé esta app usará menos de 1MB en meses.

**¿Qué pasa si los dos registramos algo al mismo tiempo?**
Gana el último que guarda. En la práctica, como los eventos del bebé son secuenciales,
esto rara vez es un problema. Si ocurre, el historial tiene borrado individual para corregir.
