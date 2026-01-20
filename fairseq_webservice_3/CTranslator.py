# -*- coding: utf-8 -*-

import os, sys, string
from ruamel.yaml import YAML
from collections import defaultdict
from sentence_splitter import SentenceSplitter
import re
import unicodedata

from placeholder_handling import set_markers, unset_markers

os.environ["MKL_CBWR"] = "AUTO,STRICT" # Batchtranslations sollen nicht von der Übersetzung einzelner Sätze abweichen



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


import ctranslate2, logging
ctranslate2.set_log_level(logging.INFO)
#('off', 'critical', 'error', 'warning (default)', 'info', 'debug', 'trace')

#from mosestokenizer import MosesTokenizer
from sacremoses import MosesTokenizer, MosesDetokenizer
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
		self.return_unks = model_info.get('return_unks')
		self.BLEU_score = model_info.get('BLEU_score')
		self.TER_score = model_info.get('TER_score')

		if self.return_unks: self.vocabs = set(open(path + '/train_vocabulary.txt').read().split('\n'))

		self.aggressive_dash_splits = model_info.get('aggressive_dash_splits')
		self.escape_xml = model_info.get('escape_xml')
		self.tokenizer_languages = model_info.get('tokenizer_languages')
		protected_pattern_filepath = model_info.get('protected_pattern_filepath')
		if protected_pattern_filepath:
			with open(os.path.join("/app", protected_pattern_filepath)) as protected_pattern_file:
				self.protected_patterns = [line.strip() for line in protected_pattern_file.readlines()]
		else:
			self.protected_patterns = None
		self.ne_placeholder_separator = model_info.get("ne_placeholder_separator", "┿")


		self.custom_nonbreaking_prefix_files = model_info.get("custom_nonbreaking_prefix_files", dict())
		self.sentence_splitter_nonbreaking_prefix_files = model_info.get('sentence_splitter_nonbreaking_prefix_files', dict())

		self.tokenizers = dict()
		self.detokenizers = dict()
		self.sentence_splitters = dict()
		for lang in set(sum([dir.split('_') for dir in self.directions], [])):
			tokenizer_language = self.tokenizer_languages[lang]
			if lang in self.custom_nonbreaking_prefix_files:
				prefix_file = self.custom_nonbreaking_prefix_files[lang]
				self.tokenizers[lang] = MosesTokenizer(tokenizer_language, custom_nonbreaking_prefixes_file=prefix_file)
			else:
				self.tokenizers[lang] = MosesTokenizer(tokenizer_language)

			self.detokenizers[lang] = MosesDetokenizer(tokenizer_language)

			if lang in self.sentence_splitter_nonbreaking_prefix_files:
				prefix_file = self.sentence_splitter_nonbreaking_prefix_files[lang]
				self.sentence_splitters[lang] = SentenceSplitter(language='xx',
													 non_breaking_prefix_file=prefix_file)
			else:
				self.sentence_splitters[lang] = SentenceSplitter(language=lang)
		
		self.placeholder_method = model_info.get("placeholder_handling_method")
		self.replace_unknowns = model_info.get("replace_unknowns", False)

	def s_split(self, lang, text):
		text_replace_special_chars = text.translate(str.maketrans('„“»«‚‘', '""""""'))
		splitted = self.sentence_splitters[lang].split(text_replace_special_chars)
		i = 0
		for sentence in splitted:
			yield text[i : i + len(sentence) + 1].strip()
			i += len(sentence)
			while i < len(text) and text[i] != ' ':
				i += 1

	def _preprocess_sentence(self, sentence, src, tgt):
		logger.info(f"Input sentence: {sentence}")
		#fakeperiod = sentence and not (sentence[-1] in string.punctuation + '…')
		fakeperiod = sentence and not unicodedata.category(sentence[-1]).startswith("P")
		if fakeperiod: sentence += '.'
		sentence, markers_information = set_markers(sentence, self.placeholder_method, self.ne_placeholder_separator)
		sentence = re.sub(r'\.(?=\w)', '. ', sentence)
		logger.info(f"marked sentence: {sentence}")
		logger.info(f"marker info: {markers_information}")
		tok_sentence = self.tokenizers[src].tokenize(sentence,
											    aggressive_dash_splits=self.aggressive_dash_splits,
												protected_patterns=self.protected_patterns,
												escape=self.escape_xml,
												return_str=False
											   )
		logger.info(f"tokenized sentence: {tok_sentence}")
		vocabs = get_words(tok_sentence)
		tok_sentence = [f"<{tgt}>"] + self.bpe.encode([' '.join(tok_sentence)], output_type=yttm.OutputType.SUBWORD)[0]
		logger.info(f"Preprocessed sentence: {tok_sentence}")
		return tok_sentence, vocabs, fakeperiod, markers_information


	def _postprocess_sentence(self, result, tgt, fakeperiod, markers_information):
		logger.info(f"model result: {result}")
		tok_translation = bpe_detokenize(result.hypotheses[0])
		logger.info(f"BPE-Detokenized sentence: {tok_translation}")
		vocabs = get_words(tok_translation)
		logger.info(f"BPE-Detokenized sentence: {tok_translation}")
		translation = self.detokenizers[tgt].detokenize(tok_translation)
		logger.info(f"Detokenized sentence: {translation}")
		translation = unset_markers(translation, self.placeholder_method, markers_information, self.ne_placeholder_separator)
		if fakeperiod: translation = translation[:-1]
		logger.info(f"Postprocessed sentence: {translation}")
		return translation, vocabs


	def translate_sentences(self, sentences, src, tgt):
		"""
		Process and translate a list of sentences.

		Args:
			sentences ([str]): List of sentences.
			src (str): Source language.
			tgt (str): Target language.

		Returns:
			translations ([str]): List of translated sentences.
			vocabs ({str}): Set of words used in the entences and the translations.
		"""

		preprocessed_sentence_information = [self._preprocess_sentence(sentence, src, tgt) for sentence in sentences]
		tok_sentences, sentences_vocabs, fakeperiod_info, sentences_markers_information = zip(*preprocessed_sentence_information)

		vocabs = set()
		for sentence_vocabs in sentences_vocabs:
			vocabs.update(sentence_vocabs)
		results = self.translator.translate_batch(tok_sentences, replace_unknowns=self.replace_unknowns, return_scores=False)
		postprocess_arguments = zip(results, fakeperiod_info, sentences_markers_information)
		processed_translation_information = [self._postprocess_sentence(result, tgt, fakeperiod, markers_information)
									   for (result, fakeperiod, markers_information) in postprocess_arguments]
		
		translations, translations_vocabs = zip(*processed_translation_information)
		
		for translation_vocabs in translations_vocabs:
			vocabs.update(translation_vocabs)

		return translations, vocabs


models, gui_models = {}, {}
for direction, locations in model_config.items():
	for i, location in enumerate(locations):
		print(location)
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

	sentences_and_line_numbers = [(sentence, i) for (i, line) in enumerate(input) for sentence in line]
	sentences, line_numbers = zip(*sentences_and_line_numbers)

	translations, vocabs = model.translate_sentences(sentences, src, tgt)

	lines_dict = defaultdict(list)
	for translation, line in zip(translations, line_numbers):
		lines_dict[line].append(translation)

	# Convert dict to list of lists (sorted by line number if needed)
	highest_line_num = max(lines_dict.keys())
	output = [lines_dict[i] for i in range(highest_line_num+1)]


	return {
		"marked_input": input,
		"marked_translation": output,
		"model": model.name,
		"unks": list(vocabs-model.vocabs) if model.return_unks else []
	}

@app.route('/info', methods=['GET'])
def info():
	output = "name", "directions", "traindate", "BLEU_score"
	return jsonify({ "webservice_version": webservice_version, "models": [{item: getattr(model, item) for item in output} for model in models.values()] })

if __name__ == '__main__':
	# app.run('0.0.0.0', 5000, ssl_context='adhoc')
	from waitress import serve
	serve(app, host="0.0.0.0", port=5000)
