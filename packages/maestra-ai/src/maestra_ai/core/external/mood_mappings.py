"""Mapeamentos editoriais de mood e gênero.

Conteúdo OPINATIVO: strings que refletem julgamento sobre o que soa bem
em cada combinação de gênero/mood. Extraído de `onboard.py` para permitir
revisão e ajuste sem tocar no algoritmo. Testado com biblioteca focada em
metal/world/folk; outras bibliotecas podem precisar ajustes aqui.

Convenções:
- `_` prefix sinaliza uso interno ao subsistema (privado ao pacote)
- Keywords e estruturas públicas (`MOOD_TAG_KEYWORDS`, `GENRE_KEYWORDS`)
  não têm prefix
"""
from __future__ import annotations

# v0.7.0: mapa gênero → lista de "mood modifiers" (complementos que fazem
# o texto final fluir). Cobertura razoável; se gênero não estiver no mapa,
# usa _FALLBACK_MOODS.
_GENRE_MOOD_TEMPLATES: dict[str, list[str]] = {
    "indie folk": ["melancólico para reflexão", "acústico para manhã"],
    "folk": ["suave para escrita", "tranquilo para fim de tarde"],
    "chamber folk": ["intimista para leitura", "melódico para introspecção"],
    "neo-classical": ["instrumental para concentração",
                      "minimalista para leitura"],
    "classical": ["orquestral para foco profundo",
                  "sinfônico para domingo lento"],
    "ambient": ["para trabalho analítico", "noturno para escrita"],
    "electronic": ["downtempo para tarde tranquila",
                   "dinâmico para treino"],
    "downtempo": ["lento para descanso", "para fim de expediente"],
    "jazz": ["suave para jantar", "noturno com piano"],
    "hip hop": ["groove para estrada", "com bateria pesada para treino"],
    "rock": ["energético para deslocamento", "clássico para garagem"],
    "indie rock": ["para tarde ao ar livre", "com guitarras para caminhada"],
    "pop": ["para pausa leve", "ensolarado para manhã"],
    "r&b": ["suave para noite", "com groove para fim de tarde"],
    "soul": ["aveludado para jantar", "clássico para domingo lento"],
    "synthwave": ["retrô para foco criativo", "dos anos 80 para viagem"],
    "post-rock": ["expansivo para contemplação",
                  "instrumental para leitura longa"],
    "techno": ["pulsante para treino", "minimalista para concentração"],
    "house": ["ritmado para fim de semana", "deep para tarde quente"],
    "world music": ["para despertar cultural", "para jantar com amigos"],
}


_FALLBACK_MOODS = [
    "para concentração",
    "para relaxar no fim do dia",
    "para caminhada matinal",
    "para pausa do trabalho",
]


# v0.9.0-alpha.5: fallback ESPECÍFICO por família quando todos os moods
# derivados já foram usados. Evita combinações desengonçadas tipo
# "alternative metal para pausa do trabalho" que o fallback global gera.
# Tentado antes de cair em `_FALLBACK_MOODS` universal.
_FALLBACK_MOODS_BY_FAMILY: dict[str, list[str]] = {
    "metal":              ["para treino", "para direção noturna", "para energia alta"],
    "world":              ["para despertar cultural", "para contemplação",
                           "para imersão cultural"],
    "classical":          ["para leitura longa", "para foco sustentado",
                           "para estudo"],
    "folk":               ["para fim de tarde", "para tarde ao ar livre",
                           "para reflexão calma"],
    "jazz":               ["para jantar", "para noite tranquila",
                           "para tarde suave"],
    "electronic-ambient": ["para trabalho analítico", "para foco silencioso",
                           "para escrita noturna"],
    "electronic-dance":   ["para treino", "para fim de semana",
                           "para energia alta"],
    "hip-hop":            ["para caminhada urbana", "para estrada",
                           "para treino"],
    "soul":               ["para fim de tarde suave", "para jantar",
                           "para noite tranquila"],
    "indie":              ["para tarde ao ar livre", "para caminhada",
                           "para reflexão calma"],
    "post-rock":          ["para contemplação", "para leitura longa",
                           "para escrita noturna"],
    "rock":               ["para deslocamento", "para treino",
                           "para energia alta"],
    "pop":                ["para manhã leve", "para pausa do dia",
                           "para humor positivo"],
}


# v0.9.0-alpha.3 (B): mood derivado de tags MB quando gênero não está no
# mapa curado. Whitelist de keywords que aparecem em tags MB e mapa de
# mood → contexto de uso. Ordem de prioridade:
# _GENRE_MOOD_TEMPLATES > _derive_mood_from_tags > _FALLBACK_MOODS.

MOOD_TAG_KEYWORDS = frozenset({
    "aggressive", "angry", "intense",
    "chill", "relaxing", "calm", "peaceful",
    "dark", "melancholic", "sad", "melancholy", "gloomy",
    "uplifting", "happy", "joyful", "cheerful",
    "energetic", "energy", "upbeat", "driving",
    "contemplative", "introspective", "reflective",
    "romantic", "sensual", "sexy",
    "epic", "cinematic", "grandiose",
    "mellow", "soft", "gentle",
    "heavy", "hard", "brutal",
    "dreamy", "ethereal", "atmospheric",
})


# Mapa mood → lista de contextos de uso (texto que vai depois do gênero).
# Sem duplicata do _GENRE_MOOD_TEMPLATES — esses vêm de mood, não gênero.
_MOOD_CONTEXT: dict[str, list[str]] = {
    "aggressive": ["para treino intenso", "para energia alta"],
    "angry":      ["para treino intenso", "para liberar tensão"],
    "intense":    ["para foco profundo", "para direção noturna"],
    "chill":      ["para pausa tranquila", "para fim de tarde"],
    "relaxing":   ["para descanso", "para tarde quieta"],
    "calm":       ["para leitura", "para respiração lenta"],
    "peaceful":   ["para meditação", "para amanhecer"],
    "dark":       ["noturno para foco", "para concentração intensa"],
    "melancholic":["para reflexão", "para introspecção"],
    "sad":        ["para processar o dia", "para reflexão"],
    "melancholy": ["para reflexão", "para contemplação"],
    "gloomy":     ["para dia chuvoso", "noturno para leitura"],
    "uplifting":  ["para começar o dia", "para manhã ensolarada"],
    "happy":      ["para manhã alegre", "para energia positiva"],
    "joyful":     ["para manhã alegre", "para bom humor"],
    "cheerful":   ["para manhã alegre", "para leveza do dia"],
    "energetic":  ["para treino", "para caminhada enérgica"],
    "energy":     ["para treino", "para despertar"],
    "upbeat":     ["para corrida", "para manhã ativa"],
    "driving":    ["para estrada", "para direção longa"],
    "contemplative":["para leitura longa", "para reflexão"],
    "introspective":["para escrita pessoal", "para introspecção"],
    "reflective": ["para fim de tarde contemplativo", "para reflexão"],
    "romantic":   ["para jantar a dois", "para noite romântica"],
    "sensual":    ["para noite tranquila", "para momento íntimo"],
    "sexy":       ["para noite tranquila", "para momento íntimo"],
    "epic":       ["para foco profundo", "para imersão criativa"],
    "cinematic":  ["para foco imersivo", "para contemplação"],
    "grandiose":  ["para imersão", "para momento épico"],
    "mellow":     ["para relaxar no fim do dia", "para tarde tranquila"],
    "soft":       ["para descanso", "para noite suave"],
    "gentle":     ["para descanso", "para despertar suave"],
    "heavy":      ["para garagem", "para direção intensa"],
    "hard":       ["para garagem", "para treino pesado"],
    "brutal":     ["para treino pesado", "para liberar energia"],
    "dreamy":     ["para trabalho criativo", "para entardecer"],
    "ethereal":   ["para entardecer contemplativo", "para leitura"],
    "atmospheric":["para trabalho analítico", "para foco silencioso"],
}


# v0.9.0-alpha.4 (C2): família de gênero — usado para rotear overrides
# de contexto. Se o gênero contém qualquer substring da key, entra na
# família. Ordem importa: testamos do mais específico para o genérico.
_GENRE_FAMILIES: list[tuple[str, str]] = [
    ("throat singing", "world"),
    ("mongolian", "world"),
    ("tuvan", "world"),
    ("celtic", "world"),
    ("latin", "world"),
    ("world music", "world"),
    ("neo-classical", "classical"),
    ("classical", "classical"),
    ("chamber", "classical"),
    ("orchestral", "classical"),
    ("symphonic", "classical"),
    ("death metal", "metal"),
    ("black metal", "metal"),
    ("doom metal", "metal"),
    ("folk metal", "metal"),
    ("metal", "metal"),
    ("hardcore", "metal"),
    ("punk", "metal"),
    ("jazz", "jazz"),
    ("bebop", "jazz"),
    ("swing", "jazz"),
    ("ambient", "electronic-ambient"),
    ("drone", "electronic-ambient"),
    ("techno", "electronic-dance"),
    ("house", "electronic-dance"),
    ("trance", "electronic-dance"),
    ("edm", "electronic-dance"),
    ("electronic", "electronic-dance"),
    ("hip hop", "hip-hop"),
    ("rap", "hip-hop"),
    ("r&b", "soul"),
    ("soul", "soul"),
    ("funk", "soul"),
    ("country", "folk"),
    ("bluegrass", "folk"),
    ("folk", "folk"),
    ("indie", "indie"),
    ("shoegaze", "indie"),
    ("post-rock", "post-rock"),
    ("post-metal", "post-rock"),
    ("rock", "rock"),
    ("pop", "pop"),
]


def _family_for_genre(genre: str) -> str | None:
    """Retorna a família do gênero, ou None se não classificado.

    Match por substring case-insensitive. Ordem de _GENRE_FAMILIES é
    do mais específico para o genérico.
    """
    lowered = genre.lower()
    for key, family in _GENRE_FAMILIES:
        if key in lowered:
            return family
    return None


# v0.9.0-alpha.4 (C2): overrides de contexto para combinações
# (família, mood) onde o contexto default do `_MOOD_CONTEXT` não casa.
# Ex: "heavy" em metal → "para garagem" faz sentido; em world music
# ou classical → não. Os contextos aqui substituem os de _MOOD_CONTEXT
# quando o match é encontrado.
_MOOD_CONTEXT_BY_FAMILY: dict[tuple[str, str], list[str]] = {
    # World music: mood "heavy/intense/aggressive/dark" redireciona
    # para contextos contemplativos/cinematográficos.
    ("world", "heavy"):       ["para foco profundo", "para contemplação"],
    ("world", "intense"):     ["para foco imersivo", "para meditação ativa"],
    ("world", "aggressive"):  ["para despertar cultural", "para energia ancestral"],
    ("world", "dark"):        ["noturno para contemplação", "para foco silencioso"],
    ("world", "epic"):        ["para imersão cultural", "para contemplação épica"],
    # Classical: moods pesados/energéticos viram contemplativos.
    ("classical", "heavy"):      ["para foco profundo", "para imersão"],
    ("classical", "intense"):    ["para estudo intenso", "para foco profundo"],
    ("classical", "aggressive"): ["para trabalho analítico", "para foco sustentado"],
    ("classical", "dark"):       ["noturno para leitura", "para escrita longa"],
    ("classical", "epic"):       ["para imersão", "para momento grandioso"],
    # Electronic-ambient: mood "energetic/upbeat" não casa — redireciona.
    ("electronic-ambient", "energetic"): ["para trabalho analítico", "para foco analítico"],
    ("electronic-ambient", "upbeat"):    ["para trabalho matinal", "para foco leve"],
    # Folk (country, bluegrass): "heavy/intense" não casa.
    ("folk", "heavy"):      ["para tarde acústica", "para fim de tarde longo"],
    ("folk", "intense"):    ["para tarde contemplativa", "para reflexão prolongada"],
    ("folk", "aggressive"): ["para tarde enérgica", "para caminhada matinal"],
}
