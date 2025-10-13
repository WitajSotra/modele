# modele
wozjewjenje modelow přełožowanskeje słužby

Structure:
- `ctranslate-ol`: CTranslator/Fairseq#2 von Olaf Langner. Containers (are supposed to) run on port 25000.
- `fairseq_webservice_3`: Fairseq#3. Reworked version of CTranslator/Fairseq#2 that also allows running LMU models and has more configuration options. Is supposed to replace Fairseq#1 and Fairseq#2 in the future. Supposed to run on port 35000.
- `sotra-lsf-df`: Fairseq#1. Webservice for running the LMU models. Supposed to run on port 3000.
- `moses-ol`: Webservice for Moses translator.
