import re
import unicodedata
from typing import Tuple, Dict, Optional, Any
import validators
from urlextract import URLExtract


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

#regex_interpunktion_nicht_satzzeichen = (
#    r"\-/()<>=´`'\"\+\*\~:_\^"
#    + r"«»‘’‚‛“”„‟‹›"
#)

regex_interpunktion_nicht_satzzeichen = (
    #r"[\-/()<>=´`\+\*\~:_\^«»‘’‚‛“”„‟‹›'@]" #
    r"[\-/()<>=\+\*\~:_\^‚‛'@]" #
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


extractor = URLExtract()
extractor.update_when_older(7)

def check_url_urlextract(text):
    urls = extractor.find_urls(text)
    if len(urls) > 0 and urls[0] == text:
        return True
    else:
        return False


def set_markers(text: str, ne_placeholder_separator: Optional[str]=None) -> Tuple[str, Dict[str, Dict[str, Any]]]:
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
    # Die generierten Zahlen sind prefixfrei.
    def next_id():
        i = 3
        while True:
            s = str(i)
            if s in banned_digit_sequences or s in used_ids:
                i += 1
                continue

            # skip if s is a prefix of an existing ID
            if any(u.startswith(s) for u in used_ids):
                i += 1
                continue

            # skip if any existing ID is a prefix of s
            if any(s.startswith(u) for u in used_ids):
                i += 1
                continue

            used_ids.add(s)
            return s

    def is_non_latin_char(ch: str) -> bool:
        # treat punctuation etc. as latin
        if re.match(regex_satzzeichen, ch):
            return False
        if re.match(regex_interpunktion_nicht_satzzeichen, ch):
            return False
        if re.match(r"[0-9]", ch):
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

    for j, p in enumerate(parts):
        if p.isspace() or p == "":
            intermediate.append({'text': p, 'ne': False})
            continue
        # p is a non-whitespace block; we will split it into latin/nonlatin runs
        runs = split_latin_nonlatin_runs(p)
        # Each run: (substring, is_nonlatin)
        for i, (substring, is_nonlatin) in enumerate(runs):
            if is_nonlatin:
                segment_info = {'text': substring, 'ne': True, 'type': 'nonlatin'}
                if len(intermediate) > 0 and re.search(r"\s$", intermediate[-1]["text"]):
                    segment_info["space_before"] = True
                else:
                    segment_info["space_before"] = False

                if i == len(runs) - 1:
                    if j >= len(parts) - 1:
                        segment_info["space_after"] = False
                    else:
                        if re.match(r"\s", parts[j+1]):
                            segment_info["space_after"] = True
                        else:
                            segment_info["space_after"] = False
                else:
                    if re.match(r"\s", runs[i+1][0]):
                        segment_info["space_after"] = True
                    else:
                        segment_info["space_after"] = False
                intermediate.append(segment_info)
            else:
                # latin/neutral run -> leave for further token-level checks (url/domain/email/number)
                intermediate.append({'text': substring, 'ne': False})
    #print("Schritt 2 (non-latin): ", intermediate)
    # ---------- Schritt 3: Für alle nicht-NE Fragmente -> Token-Splitting per Leerzeichen (schon segmentiert),
    # aber einzelne parts enthalten bereits keine Whitespace; wir verarbeiten diese non-NE-Parts tokenweise ----------
    final_parts = []
    #for item in result_parts:
    for i, item in enumerate(intermediate):
        if item['ne'] or item['text'].isspace():
            final_parts.append(item)
            continue
        frag = item['text']  # dieser Block enthält keine non-latin chars und keine spaces
        # Entferne ggf. Satzzeichen am Ende des Tokens (schritt 3b)
        # Wir entfernen *fortlaufend* am Ende, aber sammeln sie, damit sie zum NE-Text gehören (ggf.)
        trailing = ''
        while frag and unicodedata.category(frag[-1]).startswith("P"):
            # use unicode categories to identify punctuation characters
            trailing = frag[-1] + trailing
            frag = frag[:-1]

        token_body = frag
        checked_as_ne = False

        segment_info = {
            "text": token_body + trailing,
        }

        if i > 0:
            segment_info["space_before"] = intermediate[i-1]["text"].isspace()
        else:
            segment_info["space_before"] = False
        
        if i < len(intermediate) - 1:
            segment_info["space_after"] = intermediate[i+1]["text"].isspace()
        else:
            segment_info["space_after"] = False

        # Prüfe Token auf URL / Email / Domain
        if token_body:
            if validators.email(token_body):
                # markiere als E-Mail (inkl. trailing Satzzeichen, wie in Schritt 3)
                segment_info["ne"] = True
                segment_info["type"] = "email"
                checked_as_ne = True
            if check_url_urlextract(token_body):
                segment_info["ne"] = True
                segment_info["type"] = "url"
                checked_as_ne = True
            #elif validators.url(token_body):
            #    segment_info["ne"] = True
            #    segment_info["type"] = "url"
            #    checked_as_ne = True
            #elif validators.domain(token_body, consider_tld=True):
            #    segment_info["ne"] = True
            #    segment_info["type"] = "domain"
            #    checked_as_ne = True

        if not checked_as_ne:
            # Wenn nicht als NE erkannt, füge ursprünglichen Token (inkl. trailing) als nicht-NE ein --
            # Schritt 4 wird danach auf alle noch-nicht-NE Fragmente angewendet.
            segment_info["ne"] = False

        final_parts.append(segment_info)
    #print("Schritt 3 (NE-Segmente):", final_parts)
    # ---------- Schritt 4: In noch-nicht-NE Fragmenten -> markiere Ziffernfolgen + optionales Interpunktionszeichen (eines aus: “.;-:,”) als NE ----------
    interpunkt = r"[.;\-:,]"
    #digit_pattern = re.compile(rf"(\d+(?:{interpunkt})?)(?!-?er|-?tych)", re.IGNORECASE)
    digit_pattern = re.compile(rf"(\d+(?:{interpunkt})?\d*)(?!-?er|-?tych)", re.IGNORECASE)

    processed_parts = []
    for i, item in enumerate(final_parts):
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
            found_number_str = m.group(1)
            if re.match(r"\d+", found_number_str) and len(found_number_str) == 1:
                # if the number is an integer < 10, don't replace it, to avoid weird problems with dual forms
                fragment_info = {'text': m.group(1), 'ne': False}
            else:
                fragment_info = {'text': m.group(1), 'ne': True, 'type': 'number'}
            if start == 0:
                if i > 0:
                    fragment_info["space_before"] = final_parts[i-1]["text"].isspace()
                else:
                    fragment_info["space_before"] = False
            else:
                fragment_info["space_before"] = False
            if end == len(s):
                if i < len(intermediate) - 1:
                    fragment_info["space_after"] = final_parts[i+1]["text"].isspace()
                else:
                    fragment_info["space_after"] = False
            else:
                fragment_info["space_after"] = False
            out_fragments.append(fragment_info)
            last_idx = end
        if last_idx < len(s):
            out_fragments.append({'text': s[last_idx:], 'ne': False})
        # falls nichts gefunden, out_fragments bleibt als original
        if not out_fragments:
            processed_parts.append(item)
        else:
            processed_parts.extend(out_fragments)
    #print("Schritt 4 (numbers): ", processed_parts)
    # ---------- Schritt 5: Für alle als NE markierten Fragmente -> ersetze durch Marker ├<type>:<id>┤ ----------
    # Erstelle output-String schrittweise und fülle mapping
    out = []
    for item in processed_parts:
        if item['ne']:
            orig = item['text']
            # hole id, die nicht bereits im Text vorkommt (banned_digit_sequences berücksichtigt)
            nid = next_id()
            mapping[nid] = {
                "text": orig,
                "space_before": item.get("space_before", False),
                "space_after": item.get("space_after", False),
            }
            out.append(f"├{nid}┤")
        else:
            out.append(item['text'])

    out_text = "".join(out)

    # ---------- Schritt 6: Ersetze "┤├" durch "┤ ├" (also direkt aufeinanderfolgende NE-Tokens ggf. trennen) ----------
    if ne_placeholder_separator:
        #out_text = out_text.replace("┤├", "┤┿├")
        out_text = out_text.replace("┤├", f"┤{ne_placeholder_separator}├")
    else:
        out_text = out_text.replace("┤├", f"┤ ├")
    out_text = out_text.replace("┤", " ")
    out_text = out_text.replace("├", " ")
    #print("mapping: ", mapping)
    # Rückgabe: text mit Markern und mapping
    return out_text, mapping


def remove_markers(text_with_markers: str,
                      mapping: Dict, ne_placeholder_separator: Optional[str]=None) -> str:
    """
    Ersetzt NE-Marker der Form <id> im gegebenen Text durch die Originalsequenzen
    aus `mapping`.

    Args:
        text_with_markers: Text, der Marker wie 3 enthält.
        mapping: Dict, das pro id die Originalsequenz liefert: mapping["3"] = "https://...",

    Returns:
        restored_text: Text, in dem alle Marker durch ihre Originalsequenzen ersetzt wurden
                       und Pseudo-Escapes zurückgetauscht sind.
    """


    def _get_original_for_id(id_str: str, interpunction_after: str) -> str:
        if id_str not in mapping:
            print(f"ID '{id_str}' not found in mapping.")
            return None  # caller will decide to leave unchanged
        val = mapping[id_str]
        if isinstance(val, dict):
            text = val.get("text", "")
            if val.get("space_before", False):
                text = " " + text
            if not interpunction_after:
                if val.get("space_after", False):
                    text = text + " "
            else:
                text = text + interpunction_after
            return text
            
        return str(val)

    def repl(m: re.Match) -> str:
        id_str = m.group(2)
        interpunction_after = m.group(4)
        orig = _get_original_for_id(id_str, interpunction_after)
        if orig is None:
            # strict was False and id not found -> leave the digit sequence unchanged
            return id_str
        return orig

    restored = ""
    intermediate = ""
    skip_next_space = False

    for ch in text_with_markers:

        if skip_next_space:
            skip_next_space = False
            if ch.isspace():
                continue

        if intermediate == "" and restored != "":
            if restored[-1].isspace() and ch.isspace():
                # skip duplicate spaces that can be added from space_after setting
                continue
            if restored[-1].isspace() and re.match(r"[\".,]", ch):
                # if the marker handling inserted a space, but the next character is a 
                # full stop, comma, or quotation, remove the space
                restored = restored[:-1]

        intermediate += ch

        for _id in mapping:
            pattern = re.compile(rf"(\s?)({_id})(\s?)([\".,])?")
            if re.search(pattern, intermediate):
                intermediate_restored = pattern.sub(repl, intermediate)
                if restored != "" and restored[-1].isspace() \
                    and intermediate_restored != "" and intermediate_restored[0].isspace():
                    intermediate_restored = intermediate_restored[1:]
                restored += intermediate_restored
                intermediate = ""
                if not mapping[_id].get("space_after", True):
                    skip_next_space = True
                break

    restored += intermediate
        

    restored = restored.replace(ESC_L, "├").replace(ESC_R, "┤")
    if ne_placeholder_separator:
        restored = restored.replace(ne_placeholder_separator, "")
    #if restore_pseudo_escapes:
    #    restored = restored.replace(esc_left, "├").replace(esc_right, "┤")




    return restored


if __name__ == "__main__":

    test_strings = [
        "Pod linkom xoyondo.com/dp/KnyNKfmxYOhLkO8 je pola 13. septembra hóčka."
        #"Z pisanym ćahom su wobydlerjo, towarstwa, dźěłarnistwa, iniciatiwy a dobroćelske zwjazki wčera w Budyšinje přećiwo prawicarskemu ekstremizmej demonstrowali.Jich podpěraše Drježdźanska kapała Banda Comunale z hudźbu."
    ]

    test_strings = [
        "Srjedź 19.lětst. ležachu",
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
        "Dafür wird in der Kernzone (ca. 3,7 % der Gesamtfläche) auf jegliche Bewirtschaftung verzichtet und Störungen werden minimiert.",
        "Die Haushaltsmittel der übrigen Organe belaufen sich für das Jahr 2000 auf 1.286.000.000."
    ]

    #test_strings = [
    #    "Z pisanym ćahom su wobydlerjo, towarstwa, dźěłarnistwa, iniciatiwy a dobroćelske zwjazki wčera w Budyšinje přećiwo prawicarskemu ekstremizmej demonstrowali.Jich podpěraše Drježdźanska kapała Banda Comunale z hudźbu.",
    #    "Mjez nimi bě tójšto Serbow.Budyšin (SN/at). „Chcemy znowa znamjo stajić za wotewrjeny Budyšin a stejimy za solidaritu, swobodu, čłowjeske prawa“, rěkaše w namołwje zwjazkarstwa tvBunt.",
    #    "A tomu přichwatani wotpowědowachu.Hłowny adresat mnohich protestnych plakatow bě strona AfD.",
    #    "Mjeztym su zamołwići za 43 projektow cyłkownje 341 000 eurow nazběrali, z čehož profitowachu tež wjele naprawow w serbskich wjeskach.Budyšin (SN/BŠe)."
    #]

    for test_string in test_strings:
        print(test_string)
        print("-------------\nescaped:")
        escaped, mapping = set_markers(test_string)
        print(escaped)
        print(mapping)
        print("-------------\nbacktranslated:")
        print(remove_markers(escaped, mapping))
        print("\n\n\n")
