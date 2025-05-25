FROM ubuntu

RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y python3-pip
RUN apt-get install -y python3-venv

WORKDIR /app
COPY L_WS.py requirements.txt .

ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install -r requirements.txt

EXPOSE 5000
ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5000", "-w", "1", "L_WS:app"]