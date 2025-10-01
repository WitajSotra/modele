from urlextract import URLExtract
import sys
import re


extractor = URLExtract()
for l, r in ('„','“'), ('‚','‘'), ('(', ')'), (' ', '.'), (' ', '?'), (' ', '!'), (' ', ','), (' ', ')'):
	extractor.add_enclosure(l, r)

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

EMOJI_PATTERN = (
	r"[\U0001F600-\U0001F64F]|" # emoticons
	r"[\U0001F300-\U0001F5FF]|" # symbols & pictographs
	r"[\U0001F680-\U0001F6FF]|" # transport & map symbols
	r"[\U0001F1E0-\U0001F1FF]|" # flags (iOS)
	r"[\U0001f926-\U0001f937]|"
	r"[\U00010000-\U0010ffff]"
)
MAIL_PATTERN    = r"[A-zěłó0-9\.\-+_]+@[A-z0-9\.\-+_]+\.[A-z]+"
HASHTAG_PATTERN = r"#[^ !@#$%^&*(),.?\":{}|<>“]+"
QUOTE_PATTERN   = r"[„“‚‘»«›‹”’]"

PH_MARK = '⟦⟧' # MATHEMATICAL SQUARE BRACKETS (U+27E6, Ps): ⟦; (U+27E7, Pe): ⟧

# Funktion zum Setzen der NE-Marker
# gibt mit Platzhaltern versehenen Satz und Rückübersetzungsinformation zurück
def set_markers(sentence):
	positions = dict()
	for url in extractor.find_urls(sentence):
		positions[sentence.find(url)] = url
		sentence = sentence.replace(url, PH_MARK, 1)

	for entity in re.findall(rf"{MAIL_PATTERN}|{HASHTAG_PATTERN}|{EMOJI_PATTERN}", sentence):
		positions[sentence.find(entity)] = entity
		sentence = sentence.replace(entity, PH_MARK, 1)

	for lquote in re.findall(rf"({QUOTE_PATTERN})\b", sentence):
		positions[sentence.find(lquote)] = lquote + '\b'
		sentence = sentence.replace(lquote, PH_MARK, 1)

	for rquote in re.findall(rf"\b({QUOTE_PATTERN})", sentence):
		positions[sentence.find(rquote)] = '\b' + rquote
		sentence = sentence.replace(rquote, PH_MARK, 1)

	return sentence, [positions[pos] for pos in sorted(positions.keys())]

def remove_markers(sentence, maps):
	sentence = sentence.replace(' '.join(list(PH_MARK)), PH_MARK)
	for map in maps:
		if map[0] == '\b':
			sentence = sentence.replace(' ' + PH_MARK, map[1], 1)
		elif len(map) > 1 and map[1] == '\b':
			sentence = sentence.replace(PH_MARK + ' ', map[0], 1)
		else:
			sentence = sentence.replace(PH_MARK, map, 1)

	sentence = sentence.translate(str.maketrans('', '', PH_MARK))

	return sentence

teststring = 'Abo sće hižo raz wo wužiwanju „dźěćacych pytanskich mašinow“ kaž blinde-kuh.de a fragFINN.de pod sylko.freudenberg@stadt.kamenz.de přemyslował/a?'
try:
	assert \
		set_markers(teststring) \
		== \
		('Abo sće hižo raz wo wužiwanju ⟦⟧dźěćacych pytanskich mašinow⟦⟧ kaž ⟦⟧ a ⟦⟧ pod ⟦⟧ přemyslował/a?', ['„\b', '\b“', 'blinde-kuh.de', 'fragFINN.de', 'sylko.freudenberg@stadt.kamenz.de'])

except AssertionError as e:
	eprint('Platzhalter passen nicht!')
	eprint(set_markers(teststring))
	sys.exit(1)