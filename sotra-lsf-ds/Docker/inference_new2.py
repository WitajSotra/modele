from pathlib import Path
import ctranslate2
from sacremoses import MosesTokenizer, MosesDetokenizer
from sentence_splitter import SentenceSplitter
import youtokentome as yttm
import socket
import json
import os
import re


version = "1.2.4 2024-12-20"

os.environ["MKL_CBWR"] = "AUTO,STRICT"
#os.environ["MKL_CBWR"] = "COMPATIBLE"

class FairseqCTranslateRunner:

    def __init__(self) -> None:

        self.verbose = 0
        #self.verbose = 1

        self.debug_info = True # Es werden in der Response zusätzliche interne Datenausgaben der Translate-Pipeline zurückgeliefert

        self.modeldir = "models1/"
        self.modeldir1 = "lmu_ds_hsb_dsb_de_2022-02-02/"
        self.modeldir2 = "witaj_mm_dsb_2022-09-18/"
        self.modeldir3 = "witaj_mm_cs_2023-02-17/"
        #self.modeldir4 = "witaj_ol_hsb_de_2023-02-26/"
        #self.modeldir5 = "witaj_ol_hsb_de_2023-02-28/"
        self.modeldir6 = "witaj_mm_cs_2023-05-08/"
        self.modeldir7 = "stojanowski_jul_2025/"
        
        self.modelpath_default = {
            "hsb_de": self.modeldir1+"hsb2de/",
            "hsb_dsb": self.modeldir1+"hsb2dsb/",
            "dsb_de": self.modeldir2+"dsb2de/",
            "dsb_hsb": self.modeldir1+"dsb2hsb/",
            #"de_hsb": self.modeldir1+"de2hsb/",
            "de_hsb": self.modeldir7+"de2hsb/",
            #"de_dsb": self.modeldir1+"de2dsb/",            
            "de_dsb": self.modeldir7+"de2dsb/",
            "cs_hsb": self.modeldir3+"cs2hsb/",
            "cs_dsb": self.modeldir3+"cs2dsb/",
            "hsb_cs": self.modeldir6+"hsb2cs/",
            "dsb_cs": self.modeldir6+"dsb2cs/",
        }

        self.modelpath_test = {
          # "hsb_de": self.modeldir5+"hsb2de/",
        }
        #fname=self.modeldir+self.modeldir4+"hsb2de/"
        #print(fname)
        #tt = ctranslate2.Translator(fname,    device="cpu") 
        self.translator_default = { pair: ctranslate2.Translator(self.modeldir+self.modelpath_default.get(pair), device="cpu") for pair in self.modelpath_default  }

        self.translator_test =    { pair: ctranslate2.Translator(self.modeldir+self.modelpath_test.get(pair),    device="cpu") for pair in self.modelpath_test  }

        self.bpe_default= { pair: yttm.BPE(model = self.modeldir+self.modelpath_default.get(pair) + "codes-yttm") for pair in self.modelpath_default }
        self.bpe_test= { pair: yttm.BPE(model = self.modeldir+self.modelpath_test.get(pair) + "codes-yttm") for pair in self.modelpath_test }


        self.tokenizer = {
            "hsb": MosesTokenizer("hsb"),
            "de": MosesTokenizer("de"),
            "dsb": MosesTokenizer("dsb"),
            "cs": MosesTokenizer("cs")
        }

        self.detokenizer = {
            "hsb": MosesDetokenizer("hsb"),
            "de": MosesDetokenizer("de"),
            "dsb": MosesDetokenizer("dsb"),
            "cs": MosesDetokenizer("cs")
        }

        self.dir_non_breaking_prefixes = "sentence_splitter/non_breaking_prefixes/"
        # wenn ein non_breaking_prefix_file angegeben ist, hat der language-Parameter keine weitere Bedeutung (darf aber trotzdem nur 2 Buchstaben haben ...)
        self.sentence_splitter = {
            "hsb": SentenceSplitter(language='xx', non_breaking_prefix_file=self.dir_non_breaking_prefixes+'hsb.txt'),
            "de": SentenceSplitter(language='de'),
            "dsb": SentenceSplitter(language='xx', non_breaking_prefix_file=self.dir_non_breaking_prefixes+'dsb.txt'),
            "cs": SentenceSplitter(language='cs')
        }

    def tokenize(self, text, src_lng):
        ret= self.tokenizer[src_lng].tokenize(text, aggressive_dash_splits=False, return_str=True, escape=False)
        return ret


    def detokenize(self, text, trg_lng):
        return self.detokenizer[trg_lng].detokenize(text.split())

    def bpe_tokenize(self, text, direction, model_env):
        bpe = self.bpe_default
        if model_env == "test":
            bpe = self.bpe_test
        ret = bpe[direction].encode([text], output_type=yttm.OutputType.SUBWORD)
        return ret[0]

    def bpe_detokenize(self, text):
        return ''.join(text.split()).replace('▁', ' ').strip()

    def add_language_token(self, text, trg_lng):
        return ["<" + trg_lng + ">"] + text

    def split_sentences(self, text, language):
        #print("split_sentences: "+text)

        if not text.endswith("\n"):
                text = text+"\n" # abschließender Zeilentrenner ist für die weiteren Schritte Voraussetzung ...

        # mark the sentences as described in Schnittstelle_Webserver_Translationscript.docx (¶ stands for newline (i. e. end of paragraph), ┊ stands for new sentence as part of a paragraph)
        marked_lines = re.split("(\n)", text.replace("¶", "")) # keep the split delimiter ...
        #print ("#0a: ",str(marked_lines))
        marked_lines = [line.replace("\n", "¶") for line in marked_lines ]  # replace sequences \n+ by ¶+
        #print ("#0b: ",str(marked_lines))
        #print ("#1: ",("".join(marked_lines).replace("\n", "\\n")))
        marked_lines1=[]
        # marked_lines enthält abwechselnd die Zeileninhalte selbst und die Zeilentrennersequenzen ¶+. 
        # In diesem Schritt werden Zeileninhalte und Zeilentrennersequenzen zusammengefügt
        for i in range(0,len(marked_lines)-1,2):
            if marked_lines[i] != "" or i < len(marked_lines)-1:
                marked_lines1.append(marked_lines[i]+marked_lines[i+1])
        #print ("#2: "+("".join(marked_lines1).replace("\n", "\\n")))

        marked_lines  = marked_lines1
        marked_lines = [self.sentence_splitter[language].split(
            line) for line in marked_lines] # marked_lines ist jetzt ein Array of Arrays ...
        #print ("marked_lines: "+str(marked_lines))
        # flatten the list; ┊ stands for end of sentence
        marked_lines = [
            item + "┊" for sublist in marked_lines for item in sublist]
        marked_lines = [line.replace("¶┊", "¶") for line in marked_lines]
        #print("marked_lines: "+str(marked_lines))
        return marked_lines

    def translate(self, source, src_lng, trg_lng, model_env):
        direction = src_lng + "_" + trg_lng
        modelpath = self.modelpath_default
        translator = self.translator_default
        sentences_bpe_pp = ''  # bpe-encoded pretty print
        
        if model_env == "test":
            modelpath = self.modelpath_test
            translator = self.translator_test
        model = ''
        errormsg = None
        output = None
        marked_input = None
        marked_output = None
        translations_debpe_pp = None
        if modelpath.get(direction):
            model = modelpath[direction]
            if self.verbose > 0:
                print("model: "+model)


            #Zeilen, die nur aus Whitespaces bestehen, verwirren den Übersetzer; "trimme" deshalb alle Zeilen
            marked_lines = source.split("\n")
            marked_lines = [line.strip() for line in marked_lines] 
            source = "\n".join(marked_lines)

            marked_lines=self.split_sentences(source, src_lng)

            sentences = [line.replace("¶", "").replace("┊", "")
                        for line in marked_lines]

            if self.verbose > 0:
                sentences_tok = [self.tokenize(sent, src_lng)
                                for sent in sentences]
                print("input: tokenized:\n", sentences_tok, "\n")

            sentences = [self.add_language_token(self.bpe_tokenize(
                self.tokenize(sent, src_lng), direction, model_env), trg_lng) for sent in sentences]

            if self.verbose > 0 or self.debug_info:
                sentences_bpe_pp = ["⚬".join(sent) for sent in sentences]
                sentences_bpe_pp = "\n".join(sentences_bpe_pp)
                sentences_bpe_pp = sentences_bpe_pp.replace("⚬▁", "▁")
                if self.verbose > 0:
                    print("input: tokenized / bpe result (pretty print):\n",
                        sentences_bpe_pp, "\n")

            translations = []
            translations = translator[direction].translate_batch(
                sentences, replace_unknowns=True)

            translations_debpe_pp = ''
            if self.verbose > 0 or self.debug_info:
                # if verbose > 0:
                #    print("raw translations:", translations)
                translations_debpe_pp = ["⚬".join(trans.hypotheses[0])
                                         for trans in translations]
                translations_debpe_pp = "\n".join(translations_debpe_pp)
                translations_debpe_pp = translations_debpe_pp.replace(
                    "⚬▁", "▁")
                if self.verbose > 0:
                    print("raw translations (pretty print):\n",
                          translations_debpe_pp, "\n")
                    translations_tmp1 = [self.bpe_detokenize(
                        " ".join(trans.hypotheses[0])) for trans in translations]
                    print("translation bpe_detokenize:\n",
                          translations_tmp1, "\n")
                    translations_tmp2 = [self.detokenize(
                        trans, trg_lng) for trans in translations_tmp1]
                    print("translation detokenize:\n", translations_tmp2, "\n")

            translations = [self.detokenize(self.bpe_detokenize(
                " ".join(trans.hypotheses[0])), trg_lng) for trans in translations]

            # if verbose > 0:
            #    print("translations; detokenize / bpe result:\n", translations, "\n")

            marked_translations = []
            for ix, translation in enumerate(translations):
                marked_input_line = marked_lines[ix]
                unmarked_input = marked_input_line.replace("¶", "").replace("┊", "")
                if unmarked_input == "":
                    marked_translation = "" # Wenn die Eingabezeile leer war, dann lösche die Übersetzung (falls der Übersetzter halluzinierte ...)
                else:
                    marked_translation = translation
                end_marker = ""
                if marked_input_line.endswith("┊"):
                    end_marker = "┊"
                elif marked_input_line.endswith("¶"):
                    end_marker = re.split("(¶+)", marked_input_line)[1] # end_marker kann auch eine sequenz von Zeilenschaltungen sein (kann eigentlich nicht passieren ...)
                marked_translations.append(marked_translation+end_marker)

            #print("#end:\n"+str(marked_translations))
            marked_input = "\n".join(marked_lines)
            output = " ".join(translations)
            marked_output = "\n".join(marked_translations)
        else:
            errormsg = "Direction '"+direction+"' not supported for model_env '"+model_env+"'"

        # print(translations)
        return (output, marked_input, marked_output, sentences_bpe_pp, translations_debpe_pp, model, errormsg)


if __name__ == "__main__":

    #from flask import Flask, escape, request
    from flask import Flask, request
    from flask_cors import CORS, cross_origin

    app = Flask(__name__)
    cors = CORS(app)
    app.config['CORS_HEADERS'] = 'Content-Type'

    runner = FairseqCTranslateRunner()

    hostname = socket.gethostname()
    print("hostname: "+hostname)
    python_filename = __file__
    print("python_filename:"+python_filename)

    from datetime import datetime, timezone

    p = Path(python_filename)
    stat_result = p.stat()
    modified = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
    # print('modified utc', modified)

    # file = open(python_filename)
    # python_src_code = file.read().replace("\n", " ")
    # file.close()
    # print (python_src_code)
    @app.route('/translate', methods=['POST'])
    def translate():

        if runner.verbose > 0:
            print("\nrequest", request, "\n")
        if request.json != None:
            print("\nrequest", request.json, "\n")

        if request.json is None or 'text' not in request.json:
            return {'error': '"text" field in JSON payload is required'}, 400

        text = request.json.get('text')
        src_lng = request.json.get('source_language', '')
        trg_lng = request.json.get('target_language', '')

        model_env = request.json.get('model_env', '')

        result = runner.translate(text, src_lng, trg_lng, model_env)
        errormsg = result[6]
        ok = True
        if errormsg != None:
            ok = False
        retval = {'ok': ok, 'translation': result[0], 'marked_input': result[1], 'marked_translation': result[2],
                  'ctranslate2_input': result[3], 'ctranslate2_output': result[4], 'model': result[5]}
        if errormsg != None:
            retval['errormsg'] = errormsg
        return retval

    @app.route('/info')
    def info():
        modelinfo_default = { }
        modelinfo_test = { }
        modelinfo = [modelinfo_default, modelinfo_test] 
        modelpath_list = [runner.modelpath_default, runner.modelpath_test]
        for i in [0,1]:
            modelpath = modelpath_list[i]
            for key in modelpath.keys():
                fname = runner.modeldir+modelpath.get(key)+'info.json'
                #print ("reading "+fname)
                if os.path.isfile(fname):
                    f = open(fname)
                    data = json.load(f)
                    print (data)
                    modelinfo[i][key] = data
                    f.close()
        return {'modelpath_default': runner.modelpath_default, 'modelinfo_default': modelinfo_default, 'modelpath_test': runner.modelpath_test, 'modelinfo_test':modelinfo_test, 'hostname': hostname, 'srcfilename': python_filename + " (modified UTC: "+str(modified)+")", 'version': version }

    @app.route('/split_sentences', methods=['POST'])
    def split_sentences():
        if request.json != None:
            print("\nrequest", request.json, "\n")
        text = request.json.get('text')
        language = request.json.get('language')
        result=runner.split_sentences(text, language)
        retval= {'sentences':result}
        return retval

    app.run('0.0.0.0', 3000)

