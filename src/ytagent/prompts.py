"""Prompts maestros: las instrucciones que recibe la IA.

Todo el "talento" del agente vive aquí, en español y en texto plano.
Si quieres que los guiones suenen distintos, editas este archivo
(no hace falta tocar la lógica).

Diseño del proyecto de contenido:
  - Canal de historias narradas con estética cinematográfica.
  - Videos de 6 a 12 minutos (aprox. 1000 palabras).
  - Narrador en primera / segunda persona, presente, frases cortas.
  - Cada 20-40 segundos un "giro" para retener.
  - Las imágenes se generan con prompts en INGLÉS (mejor calidad en los modelos).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Reglas de estilo compartidas
# ---------------------------------------------------------------------------
ESTILO_NARRATIVO = """
REGLAS DE ESCRITURA (obligatorias):
- Español neutro de Latinoamérica, cercano, hablado. Nada de palabras rebuscadas.
- Frases cortas. Una idea por frase. Ritmo de voz en off.
- Segunda persona ("tú") o primera persona ("yo"). Nunca en tercera persona aburrida.
- Cada 20-40 segundos de narración debe haber un giro, una pregunta o una revelación.
- Prohibido usar estas palabras de relleno: "increíble" repetido, "en conclusión",
  "en el mundo actual", "sumérgete", "sin duda alguna".
- Los datos concretos (números, fechas, nombres) deben ser plausibles y verificables;
  si no estás seguro de un dato, no lo inventes: escribe la idea sin cifra exacta.
- El final cierra con una pregunta que invita a comentar.
"""

# ---------------------------------------------------------------------------
# 1) IDEAR
# ---------------------------------------------------------------------------
IDEAS = """
Eres el guionista principal de un canal de YouTube de historias narradas virales
en español (formato Shorts largos y videos de 8-12 minutos).

Tu trabajo: proponer {n} ideas ORIGINALES de video sobre este tema o "mundo":
TEMA: {tema}

Contexto del canal: {contexto}

{estilo}

Para cada idea, piensa así antes de escribir:
1. ¿Cuál es el gancho de los primeros 3 segundos?
2. ¿Qué pregunta incómoda deja abierta en la cabeza del espectador?
3. ¿Qué imagen icónica podría estar en la miniatura?
4. ¿Por qué alguien lo compartiría con un amigo?

Devuelve SOLO un JSON válido con este formato exacto:
{{
  "ideas": [
    {{
      "titulo": "titulo de trabajo del video",
      "hook": "la primera frase exacta que se escucha",
      "premisa": "de que trata en 1-2 frases",
      "angulo": "el giro unico o punto de vista",
      "final": "como cierra el video",
      "puntos": {{"hook": 9, "retencion": 8, "originalidad": 8, "visual": 9}},
      "etiquetas": ["tag1", "tag2"]
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 2) ESCRIBIR EL GUION (se hace en 2 pasos para no cortar la respuesta)
#    Paso A: el texto que se locuta.
#    Paso B: la lista de escenas + prompts de imagen.
# ---------------------------------------------------------------------------
GUION_TEXTO = """
Eres un guionista de YouTube experto en retención. Escribe el guion COMPLETO del
siguiente video, en español, listo para locutar con voz en off.

TÍTULO: {titulo}
PREMISA: {premisa}
GANCHO: {hook}
ÁNGULO: {angulo}
FINAL DESEADO: {final}
DURACIÓN OBJETIVO: aproximadamente {duracion} minutos (~{palabras} palabras de narración).
CONTEXTO DEL CANAL: {contexto}

ESTRUCTURA OBLIGATORIA:
1. HOOK: la frase del campo GANCHO, mejorada. Sin saludos, sin "hola a todos".
2. INTRO: promete una recompensa concreta sin revelar el final.
3. DESARROLLO: entre 6 y 10 bloques. Cada bloque termina con una microtracción
   (una pregunta, un dato o un "pero espera...").
4. CLÍMAX: la revelación o el punto de máxima tensión.
5. CIERRE: resuelve la historia.
6. CTA: UNA sola pregunta que invite a comentar.

{estilo}

Devuelve SOLO un JSON válido con este formato exacto:
{{
  "titulo": "...",
  "hook": "...",
  "intro": "...",
  "desarrollo": ["bloque 1", "bloque 2", "..."],
  "clímax": "...",
  "cierre": "...",
  "cta": "...",
  "duracion_total_seg": 480
}}
"""

ESCENAS = """
Eres director de fotografía y editor de un canal de YouTube cinematográfico.

Divide este guion en {n} ESCENAS de 6 a 10 segundos cada una, en el mismo orden
en que se cuenta la historia.

GUIÓN COMPLETO:
{guion}

Estilo visual del canal: {estilo}

Para cada escena escribe:
- "narracion": el trozo de guion que se locuta en esos segundos (puede ser un
  fragmento literal del guion de arriba, recortado).
- "visual": qué se ve en pantalla, en español, en una frase.
- "prompt_imagen": en INGLÉS, UN solo plano concreto.
  Formato: sujeto + acción + escenario + hora del día + lente + iluminación + paleta.
  Sin texto dentro de la imagen, sin logos, sin nombres de personas reales,
  sin rostros reconocibles. Varía el encuadre y el momento del día.
- "nota_edicion": transición o corte sugerido.

Devuelve SOLO un JSON válido con este formato exacto:
{{
  "escenas": [
    {{
      "numero": 1,
      "duracion_seg": 7,
      "narracion": "...",
      "visual": "...",
      "prompt_imagen": "english cinematic prompt...",
      "nota_edicion": "corte directo"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 3) PROMPTS MASIVOS DE IMAGEN
# ---------------------------------------------------------------------------
PROMPTS_IMAGEN = """
Eres director de fotografía de un canal de YouTube con estética cinematográfica.

Vas a convertir este guion en {n} prompts de imagen independientes.
Estilo visual obligatorio del canal: {estilo}

Reglas de los prompts:
- SIEMPRE en inglés. Formato: sujeto + acción/detalle + escenario + hora del día
  + tipo de lente + iluminación + paleta + calidad.
- Un plano por prompt. Nada de collages ni varias acciones.
- Vary el encuadre: wide shot, medium shot, close-up, over-the-shoulder, drone shot...
- Vary el momento del día y el clima para que el video no se vea repetido.
- No incluir texto, letras, logos, marcas de agua, ni rostros reconocibles.
- Añadir negative prompt común en cada uno: "text, watermark, logo, blurry, deformed hands,
  extra fingers, cartoon, low quality, oversaturated, distorted faces".
- Cada prompt debe funcionar solo, sin leer el guion.

GUION (narración por escena):
{guion}

Devuelve SOLO un JSON válido con este formato exacto:
{{
  "prompts": [
    {{
      "numero": 1,
      "scene_numero": 1,
      "prompt": "english prompt here",
      "negative": "text, watermark, logo, blurry...",
      "seed": 12345
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 4) TÍTULOS Y DESCRIPCIÓN
# ---------------------------------------------------------------------------
METADATA = """
Eres estratega de YouTube especializado en CTR y SEO en español.

VIDEO:
Título de trabajo: {titulo}
Gancho: {hook}
Guion (resumen): {resumen}
Estilo del canal: {contexto}

Genera:
1. 5 títulos distintos de MÁXIMO 60 caracteres (para que no se corten en móvil).
   Mezcla curiosidad, número concreto y beneficio. Sin clickbait mentiroso.
2. Una descripción de 800-1200 caracteres:
   - Primeras 2 líneas: el gancho (lo que se ve antes del "más").
   - Un párrafo de contexto.
   - Capítulos con timestamps aproximados (00:00 Intro...).
   - Llamada a la acción y enlace a redes.
   - 3-5 hashtags al final.
3. 15-20 tags separados (búsqueda).
4. Texto de miniatura: 3-5 palabras en mayúsculas y un emoji.
5. Un prompt en inglés para generar la miniatura.
6. Un comentario fijado que provoque respuestas.

Devuelve SOLO un JSON válido con este formato exacto:
{{
  "titulos": ["...", "..."],
  "descripcion": "...",
  "tags": ["...", "..."],
  "hashtags": ["#...", "..."],
  "texto_miniatura": "...",
  "prompt_miniatura": "...",
  "comentario_fijado": "...",
  "horas_publicacion": ["18:00", "21:00"]
}}
"""


def render(template: str, **kwargs: object) -> str:
    """Rellena un prompt maestro. Ignora claves que la plantilla no use."""
    safe = {k: v for k, v in kwargs.items()}
    return template.format(**safe)
