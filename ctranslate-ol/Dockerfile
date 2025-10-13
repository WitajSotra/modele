FROM python:3.9

WORKDIR /app

RUN pip config --user set global.progress_bar off
RUN pip install Cython
RUN pip install flask
RUN pip install flask-cors
RUN pip install waitress
RUN pip install urlextract
RUN pip install opus-fast-mosestokenizer
RUN pip install ctranslate2
RUN pip install youtokentome
RUN pip install ruamel.yaml

COPY models /app/models

COPY nonbreaking_prefixes/nonbreaking_prefix.* /usr/local/lib/python3.9/site-packages/mosestokenizer/share/nonbreaking_prefixes/
COPY nonbreaking_prefixes/protected_pattern /usr/local/lib/python3.9/site-packages/mosestokenizer/share

COPY CTranslator.py /app/

CMD ["python", "CTranslator.py"]
