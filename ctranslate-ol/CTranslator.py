# -*- coding: utf-8 -*-

import os, sys, string
from ruamel.yaml import YAML

os.environ["MKL_CBWR"] = "AUTO,STRICT" # Batchtranslations sollen nicht von der Übersetzung einzelner Sätze abweichen

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

def set_version(vstore):
	import datetime
	version = open(vstore, 'r').readline()
	v_num, v_date = version.split()
	f_date = str(datetime.datetime.fromtimestamp(os.stat(__file__).st_mtime)).split()[0]
	if not v_date == f_date:
		major, minor = v_num.rsplit('.', 1)
		version = f'{major}.{int(minor) + 1} {f_date}'
		with open(vstore, 'w') as f: f.write(version)
	return version

from urlextract import URLExtract
extractor = URLExtract()
for l, r in ('„','“'), ('‚','‘'), ('(', ')'), (' ', '.'), (' ', '?'), (' ', '!'), (' ', ','), (' ', ')'):
	extractor.add_enclosure(l, r)

import re
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

import ctranslate2, logging
ctranslate2.set_log_level(logging.INFO)
#('off', 'critical', 'error', 'warning (default)', 'info', 'debug', 'trace')

from mosestokenizer import MosesTokenizer
import youtokentome as yttm

# in version.txt kann man nach Belieben eine Versionsnummer nach dem Muster des Beschreibungs-Dokuments setzen.
# Die letzte(n) Stelle(n) der Versionsnummer und das Datum pflegen sich automatisch
webservice_version = set_version('version.txt')
modelpath = 'models'
model_config_file = 'model_config.yaml'

# model_config.yaml listet pro gültiger Übersetzungsrichtung auf, in welchen Verzeichnissen Modelle für diese Richtung einsetzbar sind
# Der erste Eintrag ist das default-Modell, welches zum Einsatz kommt, wenn bei der Übersetzungsanfrage kein Modell spezifiziert wurde
# Editierende von model_config.yaml sind für sinnvolle und gültige Einträge verantwortlich!
model_config = YAML().load(open(f'{modelpath}/{model_config_file}'))
valid_directions = set(model_config.keys())
valid_sources, valid_targets = map(set, zip(*(dir.split('_') for dir in valid_directions)))

class model:
	def __init__(self, location, default=False):
		path = modelpath + '/' + location
		model_info = YAML().load(open(path + '/model_info.yaml'))
		self.location = location
		self.default = default
		self.translator = ctranslate2.Translator(path, device="cpu")
		self.bpe = yttm.BPE(model = path + '/codes-yttm')
		self.name = model_info.get('name')
		self.directions = model_info.get('directions')
		self.trainer = model_info.get('trainer')
		self.traindate = model_info.get('traindate')
		self.ext = model_info.get('ext')
		self.BLEU_score = model_info.get('BLEU_score')
		self.TER_score = model_info.get('TER_score')
		if self.ext: self.vocabs = set(open(path + '/train_vocabulary.txt').read().split('\n'))
		self.tokenizers=dict()
		for lang in set(sum([dir.split('_') for dir in self.directions], [])):
			self.tokenizers[lang] = MosesTokenizer(lang, aggressive_dash_splits=model_info.get('aggressive_dash_splits'), url_handling=False, verbose=True) # user_dir='nonbreaking_prefixes'

	def s_split(self, lang, text):
		splitted = self.tokenizers[lang].split(text.translate(str.maketrans('„“»«‚‘', '""""""')))
		i = 0
		for sentence in splitted:
			yield text[i : i + len(sentence) + 1].strip()
			i += len(sentence)
			while i < len(text) and text[i] != ' ':
				i += 1

	def s_translate(self, sentence, src, tgt):
		fakeperiod = sentence and not (sentence[-1] in string.punctuation + '…')
		if fakeperiod: sentence += '.'
		if self.ext: sentence, maps = set_markers(sentence)
		tok_sentence = self.tokenizers[src].tokenize(sentence)
		# tok_sentence = ' '.join(tok_sentence).replace(' '.join(list(PH_MARK)), PH_MARK).split()
		vocabs = get_words(tok_sentence)
		tok_sentence = [f"<{tgt}>"] + self.bpe.encode([' '.join(tok_sentence)], output_type=yttm.OutputType.SUBWORD)[0]
		results = self.translator.translate_batch([tok_sentence], replace_unknowns=False, return_scores=False) # repetition_penalty=2
		# eprint(results[0].scores[0])
		tok_translation = bpe_detokenize(results[0].hypotheses[0])
		vocabs.update(get_words(tok_translation))
		translation = self.tokenizers[tgt].detokenize(tok_translation)
		if self.ext: translation = remove_markers(translation, maps)
		if fakeperiod: translation = translation[:-1]
		return translation.translate(str.maketrans('', '', PH_MARK)), vocabs

models, gui_models = {}, {}
for direction, locations in model_config.items():
	for i, location in enumerate(locations):
		m = model(location, default = i==0)
		models[m.name] = m
		if i==0: gui_models[direction] = m.name
del m

modelnames = set(models.keys())

# Sind alle Modelle vorhanden und konfiguriert?
assert set(model.location for model in models.values()) == set(os.listdir(modelpath)) - {model_config_file}

def bpe_detokenize(tokens):
	return ''.join(tokens).replace('▁', ' ').strip().split()

def prepareTranslationInputText(text):
	text = text.translate(str.maketrans(' ', ' ', '\u00AD\u200B\r')) # SOFT HYPHEN (U+00AD); ZERO WIDTH SPACE (U+200B); \r verwirrt bisweilen die Übersetzer ...
	text = re.sub(r"[ \t]+", " ", text)
	for f, r in ('Ä','Ä'), ('Ö','Ö'), ('Ü','Ü'), ('ä','ä'), ('ö','ö'), ('ü','ü'), ('ﬀ','ff'), ('ﬁ','fi'), ('ﬂ','fl'), ('ﬅ','ft'):
		if f in text:
			text = text.replace(f, r)
	return text.replace(" \n", "\n")

def get_words(tokens):
	return set(token.translate(str.maketrans('', '', '.')) for token in tokens if not token.isnumeric())

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
app.config["DEBUG"] = False
CORS(app)

@app.route('/translate', methods=['POST'])
def translate_text():
	reqdata = request.get_json()
	wrong_params = set(reqdata.keys()) - {'source_language', 'target_language', 'model', 'text', 'debug'}
	if wrong_params: return { "errormsg": f'wrong parameter{"s" if len(wrong_params)>1 else ""} {" ".join(wrong_params)}' }

	src = reqdata.get('source_language')
	if src is None: return { "errormsg": 'missing source language' }
	if not src in valid_sources: return { "errormsg": f'{src} is not a valid source language' }

	tgt = reqdata.get('target_language')
	if tgt is None: return { "errormsg": 'missing target language' }
	if not tgt in valid_targets: return { "errormsg": f'{tgt} is not a valid target language' }

	direction = src + '_' + tgt
	if not direction in valid_directions: return { "errormsg": f'translations from {src} to {tgt} are not supported' }

	modelname = reqdata.get('model')
	if modelname is None:
		model = models[gui_models[direction]]
	else:
		if modelname in modelnames:
			model = models[modelname]
			if not direction in model.directions: return { "errormsg": f"wrong combination: model {modelname} doesn't support direction {direction}" }
		else:
			return { "errormsg": f'model {modelname} is not available' }

	text = reqdata.get('text')
	if text is None or len(str(text)) == 0: return { "errormsg": 'nothing to do' }
	if not type(text) is str: return { "errormsg": f"'text': wrong type {type(text)}" }

	debug = reqdata.get('debug')
	if debug is not None:
		if not type(debug) is bool : return { "errormsg": f"'debug': you specified {debug} ({type(debug)}) but 'debug' should be true or false" }
		if debug: return { "errormsg": "content for option 'debug' not specified => no operation so far" }

	input = [list(model.s_split(src, line)) if len(line) else [] for line in prepareTranslationInputText(text).rstrip().split('\n')]

	output, vocabs = [], set()
	for line in input:
		items = []
		if line:
			for sentence in line:
				(lambda x, y: (items.append(x), vocabs.update(y))) (*model.s_translate(sentence, src, tgt))
		output.append(items)

	return {
		"marked_input": input,
		"marked_translation": output,
		"model": model.name,
		"unks": list(vocabs-model.vocabs) if model.ext else []
	}

@app.route('/info', methods=['GET'])
def info():
	output = "name", "directions", "traindate", "BLEU_score"
	return jsonify({ "webservice_version": webservice_version, "models": [{item: getattr(model, item) for item in output} for model in models.values()] })

if __name__ == '__main__':
	# app.run('0.0.0.0', 5000, ssl_context='adhoc')
	from waitress import serve
	serve(app, host="0.0.0.0", port=5000)
