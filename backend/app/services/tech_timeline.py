"""Technology introduction dates for resume anachronism checks.

Every recognized technology — languages, frameworks, cloud services,
databases, DevOps tools, and AI products — may appear on a job only when
that job was still running on or after the tool's public release month.
The same rule covers the summary and skills list: a tool may be named
there only when at least one job overlaps its release. Violations are
deleted after generation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.services.career_tenure import parse_job_date_range

# Public release month (the first of that month). Dates are biased slightly
# late when the exact day is fuzzy. A name is omitted only when the bare
# word would hit ordinary English ("go", "express", "c", "r", "spring" is
# kept because resumes mean the framework).
TECH_INTRODUCED: dict[str, date] = {
    # Languages
    "python": date(1991, 2, 1),
    "javascript": date(1995, 12, 1),
    "typescript": date(2012, 10, 1),
    "java": date(1995, 5, 1),
    "kotlin": date(2016, 2, 1),
    "swift": date(2014, 6, 1),
    "golang": date(2009, 11, 1),
    "rust": date(2015, 5, 1),
    "php": date(1995, 6, 1),
    "ruby": date(1995, 12, 1),
    "scala": date(2004, 1, 1),
    "c++": date(1985, 10, 1),
    "c#": date(2000, 6, 1),
    "perl": date(1987, 12, 1),
    "dart": date(2011, 10, 1),
    "objective-c": date(1984, 1, 1),
    "elixir": date(2012, 1, 1),
    "haskell": date(1990, 1, 1),
    "clojure": date(2007, 10, 1),
    "julia": date(2012, 2, 1),
    "groovy": date(2003, 1, 1),
    "solidity": date(2014, 8, 1),
    "zig": date(2016, 2, 1),
    # Frameworks and UI
    "react": date(2013, 5, 1),
    "react native": date(2015, 3, 1),
    "angular": date(2010, 10, 1),
    "vue": date(2014, 2, 1),
    "vue.js": date(2014, 2, 1),
    "next.js": date(2016, 10, 1),
    "nextjs": date(2016, 10, 1),
    "nuxt": date(2016, 10, 1),
    "django": date(2005, 7, 1),
    "flask": date(2010, 4, 1),
    "fastapi": date(2018, 12, 1),
    "spring": date(2004, 3, 1),
    "spring boot": date(2014, 4, 1),
    "express.js": date(2010, 11, 1),
    "expressjs": date(2010, 11, 1),
    "rails": date(2004, 7, 1),
    "ruby on rails": date(2004, 7, 1),
    "laravel": date(2011, 6, 1),
    "nestjs": date(2017, 5, 1),
    "svelte": date(2016, 11, 1),
    "dotnet": date(2002, 2, 1),
    ".net": date(2002, 2, 1),
    "asp.net": date(2002, 1, 1),
    "blazor": date(2018, 2, 1),
    "ember": date(2011, 12, 1),
    "backbone": date(2010, 10, 1),
    "gatsby": date(2015, 7, 1),
    "remix": date(2021, 11, 1),
    "flutter": date(2018, 12, 1),
    "electron": date(2013, 4, 1),
    "three.js": date(2010, 4, 1),
    "d3.js": date(2011, 2, 1),
    "bootstrap": date(2011, 8, 1),
    "tailwind": date(2017, 11, 1),
    "tailwindcss": date(2017, 11, 1),
    "material ui": date(2014, 10, 1),
    "ant design": date(2016, 1, 1),
    "styled-components": date(2016, 10, 1),
    "webpack": date(2012, 3, 1),
    "vite": date(2020, 4, 1),
    "esbuild": date(2020, 2, 1),
    "rollup": date(2015, 5, 1),
    "babel": date(2014, 9, 1),
    "eslint": date(2013, 6, 1),
    "prettier": date(2017, 1, 1),
    "jest": date(2014, 5, 1),
    "vitest": date(2021, 12, 1),
    "mocha": date(2011, 11, 1),
    "pytest": date(2004, 1, 1),
    "junit": date(1997, 1, 1),
    "playwright": date(2020, 1, 1),
    "cypress": date(2017, 10, 1),
    "selenium": date(2004, 1, 1),
    "node.js": date(2009, 5, 1),
    "nodejs": date(2009, 5, 1),
    "deno": date(2018, 6, 1),
    "bun": date(2022, 7, 1),
    "npm": date(2010, 1, 1),
    "pnpm": date(2017, 1, 1),
    "yarn": date(2016, 10, 1),
    "pydantic": date(2017, 6, 1),
    "celery": date(2009, 4, 1),
    "sqlalchemy": date(2006, 2, 1),
    "prisma": date(2020, 6, 1),
    "hibernate": date(2001, 1, 1),
    "entity framework": date(2008, 8, 1),
    # Cloud
    "aws": date(2006, 3, 1),
    "amazon web services": date(2006, 3, 1),
    "azure": date(2010, 2, 1),
    "gcp": date(2008, 4, 1),
    "google cloud": date(2008, 4, 1),
    "heroku": date(2007, 1, 1),
    "digitalocean": date(2011, 9, 1),
    "cloudflare": date(2010, 9, 1),
    "vercel": date(2015, 4, 1),
    "netlify": date(2015, 3, 1),
    "oracle cloud": date(2016, 9, 1),
    "ibm cloud": date(2014, 2, 1),
    "alibaba cloud": date(2009, 9, 1),
    "s3": date(2006, 3, 1),
    "ec2": date(2006, 8, 1),
    "aws lambda": date(2014, 11, 1),
    "amazon api gateway": date(2015, 7, 1),
    "cloudfront": date(2008, 11, 1),
    "rds": date(2009, 10, 1),
    "dynamodb": date(2012, 1, 1),
    "cloudwatch": date(2009, 5, 1),
    "vpc": date(2009, 8, 1),
    "ecs": date(2014, 11, 1),
    "eks": date(2018, 6, 1),
    "fargate": date(2017, 11, 1),
    "amazon aurora": date(2014, 11, 1),
    "aws glue": date(2017, 8, 1),
    "amazon athena": date(2016, 11, 1),
    "kinesis": date(2013, 11, 1),
    "sqs": date(2006, 7, 1),
    "sns": date(2010, 4, 1),
    "eventbridge": date(2019, 7, 1),
    "step functions": date(2016, 12, 1),
    "cloudformation": date(2011, 2, 1),
    "azure functions": date(2016, 3, 1),
    "azure devops": date(2018, 9, 1),
    "cosmos db": date(2017, 5, 1),
    "aks": date(2017, 10, 1),
    "gke": date(2014, 11, 1),
    "cloud run": date(2019, 4, 1),
    "google cloud functions": date(2017, 3, 1),
    "pub/sub": date(2015, 3, 1),
    "pubsub": date(2015, 3, 1),
    "sagemaker": date(2017, 11, 1),
    "vertex ai": date(2021, 5, 1),
    "amazon bedrock": date(2023, 4, 1),
    "aws bedrock": date(2023, 4, 1),
    "azure openai": date(2023, 1, 1),
    # Databases and data
    "postgresql": date(1996, 7, 1),
    "postgres": date(1996, 7, 1),
    "mysql": date(1995, 5, 1),
    "mariadb": date(2009, 12, 1),
    "sqlite": date(2000, 8, 1),
    "sql": date(1974, 1, 1),
    "nosql": date(2009, 1, 1),
    "sql server": date(1989, 1, 1),
    "oracle": date(1979, 1, 1),
    "mongodb": date(2009, 2, 1),
    "redis": date(2009, 5, 1),
    "memcached": date(2003, 5, 1),
    "elasticsearch": date(2010, 2, 1),
    "opensearch": date(2021, 7, 1),
    "solr": date(2006, 1, 1),
    "cassandra": date(2008, 7, 1),
    "couchbase": date(2011, 2, 1),
    "couchdb": date(2005, 4, 1),
    "neo4j": date(2007, 1, 1),
    "dynamodb": date(2012, 1, 1),
    "firestore": date(2017, 10, 1),
    "firebase": date(2012, 4, 1),
    "supabase": date(2020, 4, 1),
    "appwrite": date(2019, 9, 1),
    "snowflake": date(2014, 10, 1),
    "bigquery": date(2010, 5, 1),
    "redshift": date(2013, 2, 1),
    "databricks": date(2013, 6, 1),
    "delta lake": date(2019, 4, 1),
    "apache iceberg": date(2018, 1, 1),
    "clickhouse": date(2016, 6, 1),
    "duckdb": date(2019, 6, 1),
    "cockroachdb": date(2017, 5, 1),
    "influxdb": date(2013, 9, 1),
    "timescaledb": date(2017, 3, 1),
    "pgvector": date(2021, 4, 1),
    "pinecone": date(2021, 1, 1),
    "weaviate": date(2019, 1, 1),
    "qdrant": date(2021, 4, 1),
    "milvus": date(2019, 10, 1),
    "chromadb": date(2022, 10, 1),
    "faiss": date(2017, 2, 1),
    "hadoop": date(2006, 4, 1),
    "spark": date(2014, 5, 1),
    "apache spark": date(2014, 5, 1),
    "flink": date(2014, 12, 1),
    "apache beam": date(2016, 6, 1),
    "apache hive": date(2010, 10, 1),
    "presto": date(2012, 11, 1),
    "trino": date(2020, 12, 1),
    "kafka": date(2011, 1, 1),
    "redpanda": date(2021, 1, 1),
    "apache pulsar": date(2016, 9, 1),
    "rabbitmq": date(2007, 2, 1),
    "activemq": date(2004, 1, 1),
    "airflow": date(2015, 6, 1),
    "dbt": date(2016, 12, 1),
    "fivetran": date(2012, 1, 1),
    "airbyte": date(2020, 1, 1),
    "prefect": date(2018, 7, 1),
    "dagster": date(2018, 7, 1),
    "luigi": date(2012, 11, 1),
    "pandas": date(2009, 1, 1),
    "numpy": date(2006, 10, 1),
    "polars": date(2021, 3, 1),
    "dask": date(2015, 1, 1),
    "matplotlib": date(2003, 1, 1),
    "plotly": date(2013, 1, 1),
    "seaborn": date(2012, 1, 1),
    "jupyter": date(2014, 1, 1),
    "google colab": date(2017, 10, 1),
    "streamlit": date(2019, 10, 1),
    "gradio": date(2019, 2, 1),
    "parquet": date(2013, 3, 1),
    "apache arrow": date(2016, 2, 1),
    "protobuf": date(2008, 7, 1),
    "avro": date(2009, 1, 1),
    # DevOps, APIs, and delivery
    "docker": date(2013, 3, 1),
    "docker compose": date(2014, 2, 1),
    "kubernetes": date(2014, 6, 1),
    "k8s": date(2014, 6, 1),
    "helm": date(2015, 11, 1),
    "terraform": date(2014, 7, 1),
    "pulumi": date(2018, 6, 1),
    "ansible": date(2012, 2, 1),
    "puppet": date(2005, 1, 1),
    "chef": date(2009, 1, 1),
    "packer": date(2013, 6, 1),
    "hashicorp vault": date(2015, 4, 1),
    "consul": date(2014, 4, 1),
    "jenkins": date(2011, 2, 1),
    "gitlab": date(2011, 10, 1),
    "github": date(2008, 4, 1),
    "github actions": date(2019, 11, 1),
    "circleci": date(2011, 1, 1),
    "travis ci": date(2011, 1, 1),
    "argo cd": date(2018, 8, 1),
    "argocd": date(2018, 8, 1),
    "istio": date(2017, 5, 1),
    "linkerd": date(2016, 1, 1),
    "envoy": date(2016, 9, 1),
    "nginx": date(2004, 10, 1),
    "prometheus": date(2015, 1, 1),
    "grafana": date(2014, 1, 1),
    "grafana loki": date(2018, 12, 1),
    "datadog": date(2011, 1, 1),
    "splunk": date(2006, 1, 1),
    "new relic": date(2008, 1, 1),
    "sentry": date(2012, 1, 1),
    "pagerduty": date(2009, 1, 1),
    "opentelemetry": date(2019, 5, 1),
    "jaeger": date(2017, 4, 1),
    "zipkin": date(2012, 6, 1),
    "kibana": date(2013, 10, 1),
    "logstash": date(2011, 1, 1),
    "podman": date(2018, 1, 1),
    "minikube": date(2016, 5, 1),
    "kustomize": date(2018, 5, 1),
    "skaffold": date(2018, 3, 1),
    "graphql": date(2015, 7, 1),
    "grpc": date(2016, 8, 1),
    "openapi": date(2015, 11, 1),
    "swagger": date(2011, 8, 1),
    "oauth": date(2007, 12, 1),
    "oauth2": date(2012, 10, 1),
    "jwt": date(2012, 1, 1),
    "saml": date(2002, 1, 1),
    "websocket": date(2011, 12, 1),
    "git": date(2005, 4, 1),
    "linux": date(1991, 9, 1),
    "bash": date(1989, 6, 1),
    "html": date(1993, 6, 1),
    "css": date(1996, 12, 1),
    "sass": date(2006, 11, 1),
    "postman": date(2012, 6, 1),
    "jira": date(2002, 1, 1),
    "confluence": date(2004, 3, 1),
    "figma": date(2016, 9, 1),
    "sketch": date(2010, 9, 1),
    "slack": date(2013, 8, 1),
    "microsoft teams": date(2017, 3, 1),
    "salesforce": date(1999, 1, 1),
    "hubspot": date(2006, 6, 1),
    "servicenow": date(2004, 1, 1),
    "zendesk": date(2007, 1, 1),
    "sharepoint": date(2001, 1, 1),
    "power bi": date(2015, 7, 1),
    "tableau": date(2003, 1, 1),
    "looker": date(2012, 1, 1),
    "metabase": date(2015, 1, 1),
    "apache superset": date(2017, 1, 1),
    "dbt": date(2016, 12, 1),
    "launchdarkly": date(2014, 1, 1),
    "optimizely": date(2010, 1, 1),
    "mixpanel": date(2009, 1, 1),
    "amplitude": date(2012, 1, 1),
    "algolia": date(2012, 1, 1),
    "meilisearch": date(2019, 1, 1),
    "typesense": date(2019, 1, 1),
    # AI and ML products
    "tensorflow": date(2015, 11, 1),
    "pytorch": date(2017, 1, 1),
    "keras": date(2015, 3, 1),
    "scikit-learn": date(2010, 1, 1),
    "sklearn": date(2010, 1, 1),
    "xgboost": date(2014, 3, 1),
    "opencv": date(2000, 6, 1),
    "spacy": date(2015, 2, 1),
    "nltk": date(2001, 1, 1),
    "huggingface": date(2016, 1, 1),
    "hugging face": date(2016, 1, 1),
    "openai": date(2015, 12, 1),
    "openai api": date(2020, 6, 1),
    "chatgpt": date(2022, 11, 1),
    "gpt-2": date(2019, 2, 1),
    "gpt-3": date(2020, 6, 1),
    "gpt-3.5": date(2022, 3, 1),
    "gpt-4": date(2023, 3, 1),
    "gpt4": date(2023, 3, 1),
    "gpt-4o": date(2024, 5, 1),
    "claude": date(2023, 3, 1),
    "claude 3": date(2024, 3, 1),
    "gemini": date(2023, 12, 1),
    "anthropic": date(2021, 2, 1),
    "mistral": date(2023, 9, 1),
    "meta llama": date(2023, 2, 1),
    "llama 2": date(2023, 7, 1),
    "llama2": date(2023, 7, 1),
    "llama 3": date(2024, 4, 1),
    "codellama": date(2023, 8, 1),
    "github copilot": date(2021, 6, 1),
    "codewhisperer": date(2022, 6, 1),
    "amazon q": date(2023, 11, 1),
    "tabnine": date(2018, 1, 1),
    "ollama": date(2023, 7, 1),
    "vllm": date(2023, 6, 1),
    "langchain": date(2022, 10, 1),
    "langgraph": date(2024, 1, 1),
    "langsmith": date(2023, 7, 1),
    "llamaindex": date(2022, 11, 1),
    "llama index": date(2022, 11, 1),
    "semantic kernel": date(2023, 3, 1),
    "crewai": date(2023, 12, 1),
    "mcp": date(2024, 11, 1),
    "model context protocol": date(2024, 11, 1),
    "retrieval augmented generation": date(2020, 5, 1),
    "retrieval-augmented generation": date(2020, 5, 1),
    "generative ai": date(2022, 1, 1),
    "llm": date(2018, 10, 1),
    "llms": date(2018, 10, 1),
    "mlops": date(2018, 1, 1),
    "mlflow": date(2018, 6, 1),
    "kubeflow": date(2017, 12, 1),
    "weights and biases": date(2018, 1, 1),
    "wandb": date(2018, 1, 1),
    "dall-e": date(2021, 1, 1),
    "dall-e 2": date(2022, 4, 1),
    "dall-e 3": date(2023, 10, 1),
    "stable diffusion": date(2022, 8, 1),
    "midjourney": date(2022, 7, 1),
    "openai whisper": date(2022, 9, 1),
    "cuda": date(2007, 2, 1),
    "onnx": date(2017, 9, 1),
    "word2vec": date(2013, 1, 1),
    "kaggle": date(2010, 4, 1),
}


@dataclass(frozen=True)
class TechRule:
    key: str
    introduced: date
    # Longer aliases first so "model context protocol" wins over bare fragments.
    aliases: tuple[str, ...]


def _build_rules() -> list[TechRule]:
    # One rule per name. Tools that share a release month must not be merged,
    # or stripping FastAPI would be reported as whichever other name shares
    # that month.
    return [
        TechRule(key=name, introduced=intro, aliases=(name,))
        for name, intro in TECH_INTRODUCED.items()
    ]


TECH_RULES: list[TechRule] = _build_rules()

# Neutral replacements when stripping anachronistic MCP wording from bullets.
_MCP_PHRASE_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bMCP[- ]compliant\b"), "enterprise"),
    (re.compile(r"(?i)\bMCP servers?\b"), "platform services"),
    (re.compile(r"(?i)\bMCP artifacts?\b"), "platform artifacts"),
    (re.compile(r"(?i)\bMCP (?:server )?governance\b"), "platform governance"),
    (re.compile(r"(?i)\bMCP registry\b"), "enterprise registry"),
    (re.compile(r"(?i)\bMCP (?:metadata|entries|deployments|concepts|onboarding|integrations?)\b"), "platform tooling"),
    (re.compile(r"(?i)\bModel Context Protocol\b"), "platform integration standards"),
    (re.compile(r"(?i)\bMCP\b"), "platform tooling"),
]

_OTHER_PHRASE_SUBS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "chatgpt": [(re.compile(r"(?i)\bChatGPT\b"), "AI assistants")],
    "gpt-4": [(re.compile(r"(?i)\bGPT-4\b"), "large language models")],
    "gpt4": [(re.compile(r"(?i)\bGPT-?4\b"), "large language models")],
    "claude": [(re.compile(r"(?i)\bClaude\b"), "AI assistants")],
    "langchain": [(re.compile(r"(?i)\bLangChain\b"), "AI orchestration tooling")],
    "llamaindex": [(re.compile(r"(?i)\bLlamaIndex\b"), "AI retrieval tooling")],
    "openai api": [(re.compile(r"(?i)\bOpenAI API\b"), "ML APIs")],
    "github copilot": [(re.compile(r"(?i)\bGitHub Copilot\b"), "developer tooling")],
}


def _alias_regex(alias: str) -> re.Pattern[str]:
    """Match the tool name, not a longer token that merely contains it.

    "gpt-4" must not hit "gpt-4o". "react" must not hit "reactive".
    "java" must not hit "javascript". Multi-word names also match dots
    and hyphens ("next.js" / "next js").
    """
    if alias.startswith("."):
        return re.compile(rf"(?i){re.escape(alias)}(?![A-Za-z0-9])")
    pieces = [piece for piece in re.split(r"[\s.]+", alias.strip()) if piece]
    if len(pieces) > 1:
        body = r"[\s.\-]+".join(re.escape(piece) for piece in pieces)
    else:
        body = re.escape(alias).replace(r"\-", r"[-\s]?")
    return re.compile(rf"(?i)(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])")


def job_allows_tech(job_dates: str, introduced: date) -> bool:
    """True if the job period could overlap the technology's existence."""
    parsed = parse_job_date_range(job_dates)
    if parsed is None:
        # Unknown dates: do not strip (avoid false positives), but prompts
        # still instruct the model to respect eras.
        return True
    _start, end = parsed
    # Compare by month: end month on/after intro month is allowed.
    return date(end.year, end.month, 1) >= date(introduced.year, introduced.month, 1)


def forbidden_techs_for_job(job_dates: str) -> list[TechRule]:
    return [rule for rule in TECH_RULES if not job_allows_tech(job_dates, rule.introduced)]


def techs_absent_from_career(experience) -> list[TechRule]:
    """Tools that no job on this resume overlaps.

    Summary and skills are not dated. A tool may be named there only when
    at least one role was still running on or after its release month.
    """
    dated = []
    for entry in experience or []:
        dates = getattr(entry, "dates", "") or ""
        if parse_job_date_range(dates):
            dated.append(dates)
    if not dated:
        return []
    return [
        rule
        for rule in TECH_RULES
        if all(not job_allows_tech(dates, rule.introduced) for dates in dated)
    ]


def _alias_present(text: str, alias: str) -> bool:
    return _alias_regex(alias).search(text) is not None


def text_mentions_forbidden(text: str, rules: list[TechRule]) -> list[TechRule]:
    hits: list[TechRule] = []
    for rule in rules:
        if any(_alias_present(text, alias) for alias in rule.aliases):
            hits.append(rule)
    return hits


def _tidy_removed_tech(text: str) -> str:
    updated = text
    updated = re.sub(r"\(\s*\)", "", updated)
    updated = re.sub(r"\[\s*\]", "", updated)
    updated = re.sub(r"\s+([,.;:])", r"\1", updated)
    updated = re.sub(r"(,\s*){2,}", ", ", updated)
    updated = re.sub(r"(?i)\b(and|or|with|using|via|including)\s+(and|or)\b", r"\1", updated)
    updated = re.sub(r"(?i)\s+(and|or)\s*([,.;])", r"\2", updated)
    updated = re.sub(r"\s{2,}", " ", updated)
    return updated.strip(" -–,;/")


def neutralize_anachronistic_text(text: str, rules: list[TechRule]) -> str:
    """Remove technology names that did not exist yet.

    Known phrases are rewritten first. Every remaining alias is then deleted,
    longest name first, so "React Native" is not reduced to a stray "Native"
    and "gpt-4" is not cut out of "gpt-4o".
    """
    updated = text
    aliases: list[str] = []
    for rule in rules:
        aliases.extend(rule.aliases)
        if any(alias in {"mcp", "model context protocol"} for alias in rule.aliases):
            for pattern, repl in _MCP_PHRASE_SUBS:
                updated = pattern.sub(repl, updated)
    seen: set[str] = set()
    for alias in sorted(aliases, key=len, reverse=True):
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        for pattern, repl in _OTHER_PHRASE_SUBS.get(key, []):
            updated = pattern.sub(repl, updated)
        updated = _alias_regex(alias).sub("", updated)
    return _tidy_removed_tech(updated)


def prompt_era_rules_block() -> str:
    """One release rule for every technology, not a single-product example."""
    return (
        "TECH ERA (HARD RULE): never mention any technology before its public release. "
        "This covers every language, framework, library, database, cloud service, "
        "DevOps tool, and AI product. A tool may appear on a job only when that job "
        "was still running on or after the tool's release month (Present = today). "
        "Summary and Skills may name it only when at least one job overlaps that month. "
        "The backend deletes every violation."
    )
