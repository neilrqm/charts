FROM python:3.12

ARG ADDITIONAL_DEP_GROUPS=
ARG POETRY=/root/.local/bin/poetry

EXPOSE 8000

COPY pyproject.toml poetry.lock /

RUN pip install --no-cache-dir --upgrade pip \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && ${POETRY} config virtualenvs.create false

WORKDIR /

RUN ${POETRY} install --no-interaction --no-ansi --only main,${ADDITIONAL_DEP_GROUPS}

WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]