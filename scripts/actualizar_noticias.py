# Lenguaje: Python 3.11+
"""Agro en 5: lee fuentes del agro, elige las 5 noticias más útiles y escribe datos/noticias.json.

Se ejecuta cada hora desde GitHub Actions. Si no encuentra noticias, conserva el archivo anterior.
"""
import datetime as dt
import html
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests

TZ_CO = dt.timezone(dt.timedelta(hours=-5))
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "datos" / "noticias.json"
ARCHIVO = RAIZ / "datos" / "archivo"
VENTANA_HORAS = 36
MAX_POR_CATEGORIA = 2
UA = {"User-Agent": "AgroEn5/1.0 (boletin agro AGRODASIN)"}


def google_news(q: str) -> str:
    # Búsqueda de Google Noticias Colombia en español, formato RSS
    return f"https://news.google.com/rss/search?q={quote_plus(q)}+when:2d&hl=es-419&gl=CO&ceid=CO:es-419"


# Cada consulta se asocia a una categoría editorial
CONSULTAS = {
    "Mercados y precios": ['precio ganado Colombia', 'precio arroz paddy', 'SIPSA DANE precios alimentos', 'precio café Colombia'],
    "Clima": ['IDEAM fenómeno El Niño agricultura', 'IDEAM lluvias alerta Caribe'],
    "Política y normas": ['MinAgricultura resolución', 'decreto sector agropecuario Colombia', 'reforma agraria Colombia ANT'],
    "Crédito y convocatorias": ['FINAGRO crédito', 'Banco Agrario productores', 'ADR convocatoria proyectos', 'convocatoria asociaciones campesinas'],
    "Sanidad": ['ICA alerta sanitaria', 'fiebre aftosa Colombia ICA', 'plaga cultivos Colombia ICA'],
    "Pesca y acuicultura": ['AUNAP pesca', 'acuicultura Colombia tilapia cachama'],
    "Agro general": ['sector agropecuario Colombia', 'campesinos Colombia producción'],
}

# Fuentes directas opcionales. VERIFICAR que cada URL responda RSS antes de activarla.
FEEDS_DIRECTOS = [
    # ("https://www.contextoganadero.com/rss.xml", "Mercados y precios"),
    # ("https://www.agronegocios.co/rss", "Agro general"),
]

PESOS = {
    r"\bprecio": 3, r"\bcr[eé]dito": 3, r"convocatoria": 4, r"\balerta": 3, r"el ni[nñ]o": 3,
    r"resoluci[oó]n": 2, r"\bdecreto": 2, r"subsidio|incentivo|alivio": 3, r"\bica\b": 2,
    r"sequ[ií]a|inundaci|lluvia": 2, r"fertilizante|insumo": 2, r"plazo|inscripci|hasta el": 3,
    r"tilapia|cachama|pesca|acuicul": 2, r"asociaci|cooperativa|econom[ií]a popular": 2,
}
REGION = r"bol[ií]var|sucre|c[oó]rdoba|magdalena|cesar|atl[aá]ntico|la guajira|mompox|momposina|la mojana|caribe|magangu"
FUENTES_PRIORITARIAS = {
    "minagricultura": 3, "ministerio de agricultura": 3, "ica": 3, "ideam": 3, "finagro": 3, "adr": 3,
    "dane": 3, "aunap": 3, "upra": 3, "contexto ganadero": 2, "agronegocios": 2, "portafolio": 2,
    "la república": 2, "el tiempo": 1, "el heraldo": 2, "el universal": 2, "fedegan": 2, "fedearroz": 2,
}
EXCLUIR = r"hor[oó]scopo|f[uú]tbol|far[aá]ndula|loter[ií]a|receta"

# Filtro de admisión (no solo de exclusión): las consultas amplias como
# "sector agropecuario Colombia" o "precio ganado Colombia" en Google
# Noticias devuelven ruido real — probado el 7/11/2026: salieron noticias
# de acoso escolar, precio de carros eléctricos, fusión bancaria
# Davivienda/DAVIbank y una huelga por vivienda, todas sin relación con
# el agro. EXCLUIR por sí solo es un juego perdido (hay que prever cada
# tema ajeno posible); en cambio esto exige que la noticia mencione algo
# del campo para calificar — se aplica a TODAS las categorías, incluidas
# las que parecen específicas (p. ej. "Política y normas" con la consulta
# "decreto sector agropecuario Colombia" también dejó pasar un nombramiento
# de un consejo departamental sin relación real con el agro).
AGRO_RELEVANTE = (
    r"agr[oí]|campes|rural|ganad|cultiv|cosech|siembr|\bfinca\b|predio|agropecuar|"
    r"\bpesca\b|acuicul|p[eé]cuari|avicult|porcicult|\bcaf[eé]\b|\bcacao\b|pl[aá]tano|"
    r"\barroz\b|\bma[ií]z\b|\byuca\b|fertilizante|\briego\b|\bideam\b|\bica\b|finagro|"
    r"banco agrario|\badr\b|minagricultura|\bumata\b|\bsipsa\b|productor(es)?|"
    r"asociaci[oó]n campesina|cooperativa|hortaliza|tilapia|cachama|avicultor"
)

# Herramienta de agrodasin.org.co que se sugiere según el tema.
# Rutas confirmadas contra el repo real (Fase 0, 7/11/2026):
#   /constitucion-asociacion/ — para quien quiere CREAR una asociación/cooperativa nueva
#   /asociacion-al-dia/       — para quien ya tiene una y necesita poner los documentos al día
# El patrón de "constituir" va primero porque sugerir_herramienta() devuelve en el
# primer match: una noticia sobre crear/formalizar debe ir a constitución, no a "al día".
SITIO = os.getenv("URL_SITIO", "https://www.agrodasin.org.co")
HERRAMIENTAS = [
    (r"secop|licitaci|pliego|contrataci[oó]n p[uú]blica|\brup\b", "Analiza el pliego con LicitIA", "https://licitia.agrodasin.org.co"),
    (r"constituir|crear.{0,20}(asociaci|cooperativa)|formalizaci[oó]n|econom[ií]a popular", "Constituye tu asociación o cooperativa", f"{SITIO}/constitucion-asociacion/"),
    (r"asociaci|cooperativa", "Pon al día los documentos de tu asociación", f"{SITIO}/asociacion-al-dia/"),
    (r"convocatoria|cr[eé]dito|finagro|banco agrario|adr|incentivo|subsidio", "Haz el diagnóstico gratuito de tu proyecto", f"{SITIO}/diagnostico/"),
    (r"el ni[nñ]o|sequ[ií]a|agua|riego|lluvia", "Guías gratis de cosecha de agua y El Niño", f"{SITIO}/biblioteca/"),
]
HERRAMIENTA_BASE = ("Recursos gratuitos en la Biblioteca AGRODASIN", f"{SITIO}/biblioteca/")


def sugerir_herramienta(n: dict) -> dict:
    texto = f"{n['titulo']} {n.get('resumen_fuente', '')}".lower()
    for patron, texto_cta, url in HERRAMIENTAS:
        if re.search(patron, texto):
            return {"texto": texto_cta, "url": url}
    return {"texto": HERRAMIENTA_BASE[0], "url": HERRAMIENTA_BASE[1]}


def limpiar(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def separar_fuente(titulo: str, fuente: str) -> tuple[str, str]:
    # Google Noticias agrega " - Medio" al final del título
    if " - " in titulo:
        base, posible = titulo.rsplit(" - ", 1)
        if len(posible) <= 40:
            return base.strip(), fuente or posible.strip()
    return titulo.strip(), fuente


def leer_feed(url: str, categoria: str) -> list[dict]:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[aviso] {url[:80]}: {e}", file=sys.stderr)
        return []
    salida = []
    for e in feedparser.parse(r.content).entries:
        fecha_t = e.get("published_parsed") or e.get("updated_parsed")
        if not fecha_t:
            continue
        fecha = dt.datetime(*fecha_t[:6], tzinfo=dt.timezone.utc)
        fuente = (e.get("source") or {}).get("title", "")
        titulo, fuente = separar_fuente(limpiar(e.get("title", "")), fuente)
        resumen = limpiar(e.get("summary", ""))
        if resumen.startswith(titulo[:30]):  # Google repite el título en el resumen
            resumen = ""
        salida.append({
            "categoria": categoria, "titulo": titulo, "resumen_fuente": resumen[:300],
            "fuente": fuente or "Fuente", "url": e.get("link", ""), "fecha": fecha.isoformat(),
        })
    return salida


def puntuar(n: dict, ahora: dt.datetime) -> float:
    texto = f"{n['titulo']} {n['resumen_fuente']}".lower()
    horas = (ahora - dt.datetime.fromisoformat(n["fecha"])).total_seconds() / 3600
    puntos = max(0.0, 10 - horas / 3.6)  # 10 puntos si es de esta hora, 0 a las 36 h
    puntos += sum(p for patron, p in PESOS.items() if re.search(patron, texto))
    if re.search(REGION, texto):
        puntos += 4
    f = n["fuente"].lower()
    puntos += max((v for k, v in FUENTES_PRIORITARIAS.items() if k in f), default=0)
    return round(puntos, 2)


def parecidas(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.72


def seleccionar(noticias: list[dict], ahora: dt.datetime, cuantas: int = 5) -> list[dict]:
    limite = ahora - dt.timedelta(hours=VENTANA_HORAS)
    candidatas = [
        n for n in noticias
        if dt.datetime.fromisoformat(n["fecha"]) >= limite and n["url"]
        and not re.search(EXCLUIR, n["titulo"].lower())
        and re.search(AGRO_RELEVANTE, f"{n['titulo']} {n['resumen_fuente']}".lower())
    ]
    for n in candidatas:
        n["puntaje"] = puntuar(n, ahora)
    candidatas.sort(key=lambda n: n["puntaje"], reverse=True)

    elegidas, por_cat = [], {}
    for n in candidatas:
        if any(parecidas(n["titulo"], e["titulo"]) for e in elegidas):
            continue
        if por_cat.get(n["categoria"], 0) >= MAX_POR_CATEGORIA:
            continue
        elegidas.append(n)
        por_cat[n["categoria"]] = por_cat.get(n["categoria"], 0) + 1
        if len(elegidas) == cuantas:
            break
    return elegidas


PROMPT = """Eres editor de un boletín agropecuario colombiano para campesinos, ganaderos, pescadores y asociaciones.
Para cada noticia escribe con tus propias palabras:
- "resumen": máximo 25 palabras, qué pasó. No copies frases del medio.
- "por_que": máximo 25 palabras, por qué le importa a un productor y qué puede hacer.
Reglas: usa SOLO el título y el extracto dados. No inventes cifras, fechas ni nombres. Si el dato no alcanza, sé general.
Lenguaje sencillo, frases cortas, trato de tú. Responde SOLO un arreglo JSON: [{"i":0,"resumen":"...","por_que":"..."}, ...]

Noticias:
"""

POR_QUE_BASE = {
    "Mercados y precios": "Úsalo para decidir cuándo vender o comprar y negociar mejor con el intermediario.",
    "Clima": "Anticipa riego, siembra y manejo de animales antes de que cambie el tiempo.",
    "Política y normas": "Puede cambiar requisitos, apoyos o reglas que aplican a tu actividad.",
    "Crédito y convocatorias": "Revisa requisitos y plazos a tiempo. Pregunta en tu UMATA o secretaría de agricultura.",
    "Sanidad": "Revisa tus animales o cultivos y reporta casos sospechosos al ICA.",
    "Pesca y acuicultura": "Afecta tu producción, tus vedas o tus ventas de pescado.",
    "Agro general": "Te ayuda a entender hacia dónde va el sector este año.",
}


def explicar(elegidas: list[dict]) -> None:
    """Agrega resumen y 'por qué te importa'. Usa la API de Claude si hay clave; si no, textos base."""
    for n in elegidas:
        # resumen_fuente queda vacío cuando Google Noticias solo repetía el
        # título (ver separar_fuente/leer_feed) — sin esto, sin clave de IA,
        # el boletín mostraba la noticia sin ningún resumen (probado el
        # 7/11/2026: las 5 noticias de la primera corrida salieron así).
        n["resumen"] = n["resumen_fuente"][:180] or n["titulo"][:180]
        n["por_que"] = POR_QUE_BASE.get(n["categoria"], "")
    clave = os.getenv("ANTHROPIC_API_KEY")
    if not clave:
        return
    lista = "\n".join(f"{i}. [{n['categoria']}] {n['titulo']} | {n['resumen_fuente'][:250]}" for i, n in enumerate(elegidas))
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": clave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.getenv("MODELO_CLAUDE", "claude-haiku-5-5"), "max_tokens": 1200,
                  "messages": [{"role": "user", "content": PROMPT + lista}]},
            timeout=60,
        )
        r.raise_for_status()
        texto = r.json()["content"][0]["text"]
        datos = json.loads(texto[texto.find("["): texto.rfind("]") + 1])
        for d in datos:
            i = int(d["i"])
            if 0 <= i < len(elegidas):
                elegidas[i]["resumen"] = d.get("resumen", elegidas[i]["resumen"]).strip()
                elegidas[i]["por_que"] = d.get("por_que", elegidas[i]["por_que"]).strip()
    except Exception as e:  # nunca frenar la publicación por la IA
        print(f"[aviso] Claude no respondió bien, uso textos base: {e}", file=sys.stderr)


def main() -> int:
    ahora = dt.datetime.now(dt.timezone.utc)
    todas = []
    for categoria, consultas in CONSULTAS.items():
        for q in consultas:
            todas += leer_feed(google_news(q), categoria)
    for url, categoria in FEEDS_DIRECTOS:
        todas += leer_feed(url, categoria)
    print(f"Leídas {len(todas)} entradas")

    elegidas = seleccionar(todas, ahora)
    if len(elegidas) < 3:
        print("[aviso] Menos de 3 noticias válidas. Conservo la edición anterior.")
        return 0
    explicar(elegidas)
    for n in elegidas:
        n["herramienta"] = sugerir_herramienta(n)

    salida = {
        "servicio": "Agro en 5 · AGRODASIN",
        "generado": ahora.isoformat(),
        "edicion": ahora.astimezone(TZ_CO).date().isoformat(),
        "noticias": [
            {k: n[k] for k in ("categoria", "titulo", "resumen", "por_que", "fuente", "url", "fecha", "puntaje", "herramienta")}
            for n in elegidas
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(salida, ensure_ascii=False, indent=2)
    SALIDA.write_text(texto, encoding="utf-8")
    (ARCHIVO / f"{salida['edicion']}.json").write_text(texto, encoding="utf-8")  # última versión del día
    # Alimenta Radar/Convocatorias del sitio con datos reales (hasta 15, últimas 36 h)
    # Mismo filtro EXCLUIR + AGRO_RELEVANTE que seleccionar() — sin esto este
    # bloque queda construido aparte y deja pasar el mismo ruido (confirmado
    # el 7/11/2026: huelga por vivienda, fusión Davivienda/DAVIbank y un
    # nombramiento de consejo departamental salieron aquí después de que el
    # filtro ya se había agregado a seleccionar(), porque esta lista no pasa
    # por esa función).
    limite = ahora - dt.timedelta(hours=VENTANA_HORAS)
    conv = [
        n for n in todas
        if n["categoria"] == "Crédito y convocatorias" and dt.datetime.fromisoformat(n["fecha"]) >= limite
        and not re.search(EXCLUIR, n["titulo"].lower())
        and re.search(AGRO_RELEVANTE, f"{n['titulo']} {n['resumen_fuente']}".lower())
    ]
    for n in conv:
        n["puntaje"] = puntuar(n, ahora)
    conv.sort(key=lambda n: n["puntaje"], reverse=True)
    unicas = []
    for n in conv:
        if not any(parecidas(n["titulo"], u["titulo"]) for u in unicas):
            unicas.append(n)
    (SALIDA.parent / "convocatorias.json").write_text(json.dumps({
        "generado": ahora.isoformat(),
        "nota": "Noticias sobre convocatorias y crédito. Verificar requisitos y plazos en la fuente oficial.",
        "items": [{k: n[k] for k in ("titulo", "fuente", "url", "fecha")} for n in unicas[:15]],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for n in salida["noticias"]:
        print(f"  {n['puntaje']:>5}  [{n['categoria']}] {n['titulo'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
