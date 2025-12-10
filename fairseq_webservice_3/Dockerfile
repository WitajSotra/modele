FROM python:3.9

WORKDIR /app

RUN pip config --user set global.progress_bar off
RUN pip install Cython
RUN pip install flask
RUN pip install flask-cors
RUN pip install waitress
RUN pip install urlextract
RUN pip install sacremoses
RUN pip install ctranslate2
RUN pip install youtokentome
RUN pip install ruamel.yaml
RUN pip install sentence_splitter
RUN pip install validators
RUN pip install urlextract


COPY models /app/models

COPY nonbreaking_prefixes/* /app/nonbreaking_prefixes/

COPY CTranslator.py /app/

COPY placeholder_handling /app/placeholder_handling

CMD ["python", "CTranslator.py"]
