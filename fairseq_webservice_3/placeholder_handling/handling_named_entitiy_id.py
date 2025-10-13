import re
import unicodedata
from typing import Tuple, Dict
import validators



latin_consonants = (
    "bcçćčdđfgğhjklłmḿnñńňpṕqrŕřsśšŝşßtţvwẃxzźžż"
    "BCÇĆČDÐFGĞHJKLŁMḾNŃŇPṔQRŔŘSŚŠŜŞTŢVWẂXZŻŹŽ"
)

latin_vowels = (
    "aáäàâãåāăąæeèêëéěęēėiìíîïīǐıïoöòóôõōŏőøœ"
    "uüùúûūůyýÿAÀÂÃÅÄÁĀĂĄÆÉĚEÊËĘĒĖIÌÍÎÏĪǏÏİ"
    "OÖÓÒÔÕŌŎŐØŒUÜÙÚÛŪŮÝŸY"
)

# Regex fragments
regex_spaces = r"\s\u00A0"   # whitespace plus NBSP
regex_brackets = r"(){}\[\]"
regex_satzzeichen = r"[.;,?!:-]"

regex_interpunktion_nicht_satzzeichen = (
    r"\-/()<>=´`'\"\+\*\~:_\^"
    + r"«»‘’‚‛“”„‟‹›"
)

regex_latin_plus_interpunktion = (
    latin_consonants
    + latin_vowels
    + regex_satzzeichen
    + regex_interpunktion_nicht_satzzeichen
    + regex_spaces
    + r"0-9"
    + r"@\$€"
)

# Pattern for marking non-latin
mark_nonlatin_pattern_str = (
    "("
    "[" + regex_latin_plus_interpunktion + "]*"
    ")"
    "("
    "[^" + regex_latin_plus_interpunktion + "]*"
    ")"
    "(.*)"
)
mark_nonlatin_pattern = re.compile(mark_nonlatin_pattern_str, re.DOTALL)

# Digit patterns
digit_chars = "0-9"
digit_interpunktion_chars = r"0-9\.;\-:,"

mark_ext_digit_pattern_str = (
    "([^" + digit_chars + "]*)"
    "("
    "[" + digit_chars + "]{0,1}"
    "[" + digit_interpunktion_chars + "]*"
    ")"
    "(.*)"
)
mark_ext_digit_pattern = re.compile(mark_ext_digit_pattern_str, re.DOTALL)
ESC_L = "╠"  # pseudo-escaped left marker
ESC_R = "╣"  # pseudo-escaped right marker






def set_markers(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Ersetzt URLs, Domains, E-Mails, Zahlenfolgen und nicht-lateinische Sequenzen
    durch interne NE-Marker der Form ├<type>:<id>┤.
    Gibt (marked_text, mapping) zurück, wobei mapping[id] = {'text': original, 'type': type}.
    """
    # ---------- 1) Pseudo-Escaping vorhandener NE-Marker ----------
    # Ersetze vorhandene "├" / "┤" durch ähnliche Zeichen, die nicht als Marker interpretiert werden.
    text_ps = text.replace("├", ESC_L).replace("┤", ESC_R)

    # ---------- Hilfsdaten ----------
    mapping: Dict[str, str] = {}
    used_ids = set()  # ids chosen so far (strings)
    # Sammle alle reinen Ziffernfolgen aus dem pseudo-escaped Text -> diese IDs vermeiden
    banned_digit_sequences = set(re.findall(r"\d+", text_ps))
    # generator für next available id (als string), überspringt banned und used
    def next_id():
        i = 1
        while True:
            s = str(i)
            if s not in banned_digit_sequences and s not in used_ids:
                used_ids.add(s)
                return s
            i += 1

    # End-Satzzeichen, die am Tokenende entfernt/gesondert betrachtet werden sollen
    end_punct = set(".!?,;:—-()\"'")  # erweiterbar

    def is_non_latin_char(ch: str) -> bool:
        if ord(ch) <= 256:
            return False
        # treat punctuation etc. as latin
        if re.match(regex_satzzeichen, ch):
            return False
        try:
            nm = unicodedata.name(ch)
        except ValueError:
            # no name -> treat as non-latin (covers many symbols)
            return True
        # If Unicode name contains 'LATIN' -> treat as Latin
        return "LATIN" not in nm

    # ---------- Helper: split a non-space block into fragments of latin vs non-latin runs ----------
    def split_latin_nonlatin_runs(s: str):
        """
        Returns list of (substring, is_nonlatin) covering the original string.
        e.g. "test🥪abcПривет" -> [("test", False), ("🥪", True), ("abc", False), ("Привет", True)]
        """
        if not s:
            return []
        fragments = []
        cur_run = s[0]
        cur_flag = is_non_latin_char(s[0])
        for ch in s[1:]:
            flag = is_non_latin_char(ch)
            if flag == cur_flag:
                cur_run += ch
            else:
                fragments.append((cur_run, cur_flag))
                cur_run = ch
                cur_flag = flag
        fragments.append((cur_run, cur_flag))
        return fragments


    # ---------- Pipeline: split input preserving whitespace ----------
    parts = re.split(r"(\s+)", text_ps)  # Teile: tokens oder whitespace (whitespace in odd indices)

    # Wir bauen eine Liste result_parts, in der für jedes parts[i] entweder:
    # - a) {'text': original, 'ne': False}
    # - b) {'text': original, 'ne': True, 'type': <type>}

    intermediate = []

    for p in parts:
        if p.isspace() or p == "":
            intermediate.append({'text': p, 'ne': False})
            continue
        # p is a non-whitespace block; we will split it into latin/nonlatin runs
        runs = split_latin_nonlatin_runs(p)
        # Each run: (substring, is_nonlatin)
        for substring, is_nonlatin in runs:
            if is_nonlatin:
                intermediate.append({'text': substring, 'ne': True, 'type': 'nonlatin'})
            else:
                # latin/neutral run -> leave for further token-level checks (url/domain/email/number)
                intermediate.append({'text': substring, 'ne': False})



    #print("b: ", result_parts)
    # ---------- Schritt 3: Für alle nicht-NE Fragmente -> Token-Splitting per Leerzeichen (schon segmentiert),
    # aber einzelne parts enthalten bereits keine Whitespace; wir verarbeiten diese non-NE-Parts tokenweise ----------
    final_parts = []
    #for item in result_parts:
    for item in intermediate:
        if item['ne'] or item['text'].isspace():
            final_parts.append(item)
            continue
        frag = item['text']  # dieser Block enthält keine non-latin chars und keine spaces
        # Entferne ggf. Satzzeichen am Ende des Tokens (schritt 3b)
        # Wir entfernen *fortlaufend* am Ende, aber sammeln sie, damit sie zum NE-Text gehören (ggf.)
        trailing = ''
        while frag and frag[-1] in end_punct:
            trailing = frag[-1] + trailing
            frag = frag[:-1]

        token_body = frag
        checked_as_ne = False

        # Prüfe Token auf URL / Email / Domain
        if token_body:
            if validators.email(token_body):
                # markiere als E-Mail (inkl. trailing Satzzeichen, wie in Schritt 3)
                final_parts.append({'text': token_body + trailing, 'ne': True, 'type': 'email'})
                checked_as_ne = True
            elif validators.url(token_body):
                final_parts.append({'text': token_body + trailing, 'ne': True, 'type': 'url'})
                checked_as_ne = True
            elif validators.domain(token_body):
                final_parts.append({'text': token_body + trailing, 'ne': True, 'type': 'domain'})
                checked_as_ne = True

        if not checked_as_ne:
            # Wenn nicht als NE erkannt, füge ursprünglichen Token (inkl. trailing) als nicht-NE ein --
            # Schritt 4 wird danach auf alle noch-nicht-NE Fragmente angewendet.
            final_parts.append({'text': (token_body + trailing), 'ne': False})

    #print("c: ", final_parts)
    # ---------- Schritt 4: In noch-nicht-NE Fragmenten -> markiere Ziffernfolgen + optionales Interpunktionszeichen (eines aus: “.;-:,”) als NE ----------
    
    
    
    interpunkt = r"[.;\-:,]"
    digit_pattern = re.compile(rf"(\d+(?:{interpunkt})?)")

    processed_parts = []
    for item in final_parts:
        if item['ne'] or item['text'].isspace():
            processed_parts.append(item)
            continue
        s = item['text']
        # Wir splitten s in Sequenzen, wobei gefundene Ziffernfolgen als separate NE-Teile markiert werden
        last_idx = 0
        out_fragments = []
        #for m in mark_ext_digit_pattern.finditer(s):
        for m in digit_pattern.finditer(s):
            start, end = m.span(1)
            if start > last_idx:
                out_fragments.append({'text': s[last_idx:start], 'ne': False})
            out_fragments.append({'text': m.group(1), 'ne': True, 'type': 'number'})
            last_idx = end
        if last_idx < len(s):
            out_fragments.append({'text': s[last_idx:], 'ne': False})
        # falls nichts gefunden, out_fragments bleibt als original
        if not out_fragments:
            processed_parts.append(item)
        else:
            processed_parts.extend(out_fragments)

    #print("d: ", processed_parts)
    # ---------- Schritt 5: Für alle als NE markierten Fragmente -> ersetze durch Marker ├<type>:<id>┤ ----------
    # Erstelle output-String schrittweise und fülle mapping
    out = []
    for item in processed_parts:
        if item['ne']:
            orig = item['text']
            # hole id, die nicht bereits im Text vorkommt (banned_digit_sequences berücksichtigt)
            nid = next_id()
            mapping[nid] = orig
            out.append(f"├{nid}┤")
        else:
            out.append(item['text'])


    out_text = "".join(out)

    # ---------- Schritt 6: Ersetze "┤├" durch "┤ ├" (also direkt aufeinanderfolgende NE-Tokens ggf. trennen) ----------
    out_text = out_text.replace("┤├", "┤┿├")
    out_text = out_text.replace("┤", "")
    out_text = out_text.replace("├", "")

    # Rückgabe: text mit Markern und mapping
    return out_text, mapping


def remove_markers(text_with_markers: str,
                      mapping: Dict[str, str]) -> str:
    """
    Ersetzt NE-Marker der Form ├<type>:<id>┤ im gegebenen Text durch die Originalsequenzen
    aus `mapping`.

    Args:
        text_with_markers: Text, der Marker wie ├url:3┤ enthält.
        mapping: Dict, das pro id die Originalsequenz liefert: mapping["3"] = "https://...",

    Returns:
        restored_text: Text, in dem alle Marker durch ihre Originalsequenzen ersetzt wurden
                       und Pseudo-Escapes zurückgetauscht sind.
    """

    # Pattern: ├<id>┤   -> wir extrahieren die id (alles bis zum nächsten ┤)


    #marker_re = re.compile(r"├([^┤]+)┤")

    #found_ids = set()

    #def repl(m: re.Match) -> str:
    #    id_ = m.group(0)
    #    if id_ not in mapping:
    #            print(f"ID '{id_}' not found in mapping.")
    #            return m.group(0)
    #    found_ids.add(id_)
    #    val = mapping[id_]
    #    orig = str(val)
    #    return orig

    ## 1) Ersetze alle Marker durch die zugehörigen Originalsequenzen
    #for id_ in mapping:
    #    marker_re = re.compile(id_)
    #    text_with_markers = marker_re.sub(repl, text_with_markers)

    ## 2) Falls bei der Ersetzung Pseudo-Escaped Marker zurückgegeben werden sollen, konvertiere sie:
    #restored = text_with_markers.replace(ESC_L, "├").replace(ESC_R, "┤")
    #restored = restored.replace("┿", "")

    #if token_only:
        # match digit sequence that is a whole token (surrounded by whitespace or string boundaries)
    #    pattern = re.compile(r"(?<!\S)(\d+)(?!\S)")
    #else:
    pattern = re.compile(r"(\d+)")

    def _get_original_for_id(id_str: str) -> str:
        if id_str not in mapping:
            #if strict:
            print(f"ID '{id_str}' not found in mapping.")
                #raise KeyError(f"ID '{id_str}' not found in mapping.")
            return None  # caller will decide to leave unchanged
        val = mapping[id_str]
        if isinstance(val, dict):
            return val.get("text", "")
        return str(val)

    def repl(m: re.Match) -> str:
        id_str = m.group(1)
        orig = _get_original_for_id(id_str)
        if orig is None:
            # strict was False and id not found -> leave the digit sequence unchanged
            return id_str
        return orig

    restored = pattern.sub(repl, text_with_markers)

    restored = restored.replace(ESC_L, "├").replace(ESC_R, "┤")
    restored = restored.replace("┿", "")
    #if restore_pseudo_escapes:
    #    restored = restored.replace(esc_left, "├").replace(esc_right, "┤")




    return restored

if __name__ == "__main__":
    test_strings = [
		"hallo 1.1 2",
		"hallo  1.1  2",
		"1<unk>witaj</unk>👨🧑(🥪). Dies ist test🥪a bernhard.baier@gmx.net. 1.",
		"bernhard1@gmx.net ;a543..4;:8-asasa123123",
		"bernhard1@gmx.net a543;5..3asasa123123",
		"dorostowa dźěłarnička a 25. lětne zeńdźenje dźěłoweho kruha za nakrajne rumy Němskeje towaršnosće za geografiju – zhromadne zarjadowanje ze Serbskim institutom.",
		" dźěłarnička a 25. lětne geografiju – zhromadne ;",
		"a543asasa123123",
		"<unk>witaj</unk>👨🧑(🥪). Dies ist test🥪a",
		"<unk>witaj</unk>👨🧑(🥪). Dies ist test🥪a bernhard.baier@gmx1.net. 47hallo11",
		"Bukowc je něhdźe  6km wulka a 88 metrow dołha wjes w formje łanowca (Waldhufendorf) a bu 1280 (mjeno naspomnjenja: Buchinwalde) prěni raz naspomnjeny. Mjeno wjeski pokazuje na sydlišćo při bukowym lěsu. Nimo ryćerkubła běchu 1777 tež hišće 6 burskich statokow, 20 chěžkarjow a 14 zahrodkowych žiwnosćerjow, pola a łuki w Bukowcu. Srjedź 19.lětstotka ležachu wokoło Bukowca 11 hatow z cyłkownej płoninu 40 hektarow a w kotrychž plahowachu so karpy.",
		"Přejemy wam tež hišće wšo dobre za #20230#, krutu strowotu🍏, wjele lubosće💞 a časa za so a tež wjele wjesela😊 a rjanych dožiwjenjow ze swójbu a přećelemi🫂.",
		"Wir wünschen euch auch noch alles Gute für #20230#, beste Gesundheit🍏, viel Liebe #22# und Zeit für uns und auch viel Spaß 😊 und schöne Erlebnisse mit Familie und Freunden🫂"
    ]

    for test_string in test_strings:
        print(test_string)
        print("-------------\nescaped:")
        escaped, mapping = set_markers(test_string)
        print(escaped)
        print("-------------\nbacktranslated:")
        print(remove_markers(escaped, mapping))
        print("\n\n\n")
