"""Tests for engine.tagging. Sentences look like real HN "Who is hiring" text."""
import json
import re
import sys
from pathlib import Path

import pytest

# Make "import engine" work no matter where pytest starts.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.tagging import clean_text, load_taxonomy, tag_text  # noqa: E402

ALLOWED_CATEGORIES = {"language", "framework", "data", "cloud_devops", "ai_ml", "practice"}
ALLOWED_SDG = {"4.3", "4.4", "8.2", "8.5", "9.5", "9.c", "7.3", "13.3", "3.d", "16.6"}


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def tags(text, taxonomy):
    return tag_text(text, taxonomy)


# ---------------------------------------------------------------- taxonomy file


def test_taxonomy_has_exactly_40_unique_skills(taxonomy):
    names = [e["skill"] for e in taxonomy]
    assert len(names) == 40
    assert len(set(names)) == 40


def test_taxonomy_entries_are_well_formed(taxonomy):
    for e in taxonomy:
        assert e["category"] in ALLOWED_CATEGORIES, e["skill"]
        assert isinstance(e["synonyms"], list), e["skill"]
        assert isinstance(e["case_sensitive"], bool), e["skill"]
        assert 1 <= len(e["sdg"]) <= 2, e["skill"]
        assert set(e["sdg"]) <= ALLOWED_SDG, e["skill"]
        assert e["sdg_reason"].strip().endswith("."), e["skill"]
        # The pattern must compile.
        re.compile(e["pattern"])


def test_taxonomy_file_is_valid_utf8_json():
    path = Path(__file__).resolve().parent.parent / "data" / "taxonomy.json"
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), list)


def test_load_taxonomy_rejects_entry_without_pattern(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"skill": "X"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_taxonomy(bad)


def test_every_name_and_synonym_tags_its_own_skill(taxonomy):
    # A synonym that does not match its own skill is a bug in the pattern.
    for e in taxonomy:
        for name in [e["skill"], *e["synonyms"]]:
            found = tag_text(f"Experience with {name} is required.", taxonomy)
            assert e["skill"] in found, f"{name!r} did not tag {e['skill']!r}"


def test_empty_text_gives_empty_set(taxonomy):
    assert tags("", taxonomy) == set()
    assert tags("We sell fresh bread and good coffee.", taxonomy) == set()


# ---------------------------------------------------------------------- Go


@pytest.mark.parametrize(
    "text",
    [
        "Our backend is Go, Rust and Kubernetes.",
        "We write services in Go/Python.",
        "Senior Golang engineer wanted.",
        "We use Go to build our payment services.",
        "Python and Go.",
    ],
)
def test_go_positive(text, taxonomy):
    assert "Go" in tags(text, taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "You will own our go to market plan.",
        "Go to market lead for EMEA.",
        "We want a Go-getter with strong sales skills.",
        "Ready to go live in Q3, so let's go build it.",
        "Our go-to-market team is growing.",
    ],
)
def test_go_negative(text, taxonomy):
    assert "Go" not in tags(text, taxonomy)


def test_go_and_rust_listed_together(taxonomy):
    assert {"Go", "Rust"} <= tags("Stack: Go, Rust, Postgres", taxonomy)


# ---------------------------------------------------------------------- R


def test_r_language_positive(taxonomy):
    found = tags("Skills: R, Python, SAS", taxonomy)
    assert {"R", "Python"} <= found
    assert "R" in tags("Statistics with R/Shiny", taxonomy)
    assert "R" in tags("We use Python and R.", taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "Join our R&D team in Berlin.",
        "Heavy investment in R&amp;D.",
        "Rust, Ruby and RStudio are not R.D.",
    ],
)
def test_r_negative(text, taxonomy):
    # The last sentence names Rust and Ruby, but never the language R alone.
    assert "R" not in tags(text, taxonomy)


# ------------------------------------------------------------ C, C++, C#


def test_c_slash_cpp_gives_both(taxonomy):
    assert {"C", "C++"} <= tags("Embedded firmware in C/C++.", taxonomy)


def test_csharp_dotnet_gives_only_csharp(taxonomy):
    found = tags("Backend in C#/.NET on Azure.", taxonomy)
    assert "C#" in found
    assert "C" not in found
    assert "C++" not in found


def test_cpp_alone_is_not_c(taxonomy):
    found = tags("Modern C++17 and CMake.", taxonomy)
    assert "C++" in found
    assert "C" not in found


def test_c_alone(taxonomy):
    assert tags("Knowledge of C and Rust.", taxonomy) >= {"C", "Rust"}
    assert "C" in tags("Linux kernel work in C.", taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "We just closed our Series C funding.",
        "Report to the C-suite and the C level team.",
        "Based in Washington, D.C. and remote friendly.",
        "Plan C was to hire later.",
    ],
)
def test_c_negative(text, taxonomy):
    assert "C" not in tags(text, taxonomy)


# ----------------------------------------------------- React vs React Native


def test_react_positive(taxonomy):
    assert "React" in tags("Frontend: React, Redux, TypeScript", taxonomy)
    assert "React" in tags("ReactJS developer", taxonomy)
    assert "React" in tags("Experience with React.js", taxonomy)


def test_react_native_is_not_react(taxonomy):
    found = tags("Build our mobile app in React Native.", taxonomy)
    assert "React Native" in found
    assert "React" not in found


def test_react_and_react_native_both(taxonomy):
    found = tags("We use React on the web and React Native on phones.", taxonomy)
    assert {"React", "React Native"} <= found


@pytest.mark.parametrize(
    "text",
    [
        "We react quickly to customer needs.",
        "Reactive programming is a plus.",
        "React quickly to incidents at night.",
    ],
)
def test_react_negative(text, taxonomy):
    assert "React" not in tags(text, taxonomy)


# ------------------------------------------------------------------- Spark


@pytest.mark.parametrize(
    "text",
    [
        "Data pipelines on Apache Spark and Kafka.",
        "Spark/Scala engineer",
        "Strong PySpark skills.",
        "Experience with Spark Streaming.",
        "Hadoop, Spark, Hive",
    ],
)
def test_spark_positive(text, taxonomy):
    assert "Spark" in tags(text, taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "We want people who spark joy in our customers.",
        "Spark joy in every release.",
        "Spark Capital led our seed round.",
        "A spark of curiosity matters more than a CV.",
    ],
)
def test_spark_negative(text, taxonomy):
    assert "Spark" not in tags(text, taxonomy)


def test_spark_before_new_paragraph_still_counts(taxonomy):
    # The paragraph tag must split the lines, so "Our" is not read as "Spark Our".
    assert "Spark" in tags("<p>Stack: Python, Spark<p>Our team is small", taxonomy)


# ------------------------------------------------------------------- Swift


@pytest.mark.parametrize(
    "text",
    [
        "iOS engineer, Swift/Objective-C",
        "Swift, Kotlin and Flutter",
        "We are moving the app to SwiftUI.",
    ],
)
def test_swift_positive(text, taxonomy):
    assert "Swift" in tags(text, taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "We promise swift delivery of every feature.",
        "Swift delivery matters to us.",
        "Taylor Swift is not on the team.",
        "Swift Navigation is a GPS company.",
        "SWIFT payments integration for banks.",
    ],
)
def test_swift_negative(text, taxonomy):
    assert "Swift" not in tags(text, taxonomy)


# --------------------------------------------------------- Java vs JavaScript


def test_java_is_not_javascript(taxonomy):
    found = tags("Backend in Java 17 and Spring.", taxonomy)
    assert "Java" in found
    assert "JavaScript" not in found


def test_javascript_is_not_java(taxonomy):
    found = tags("Full stack JavaScript and Node.js", taxonomy)
    assert "JavaScript" in found
    assert "Java" not in found
    assert "Node.js" in found


def test_java_and_javascript_both(taxonomy):
    assert {"Java", "JavaScript"} <= tags("Java, JavaScript, SQL", taxonomy)


def test_nodejs_does_not_count_as_javascript(taxonomy):
    # "Node.js" is its own skill. The ".js" must not leak into JavaScript.
    found = tags("We run Node.js and Express.", taxonomy)
    assert "Node.js" in found
    assert "JavaScript" not in found


# ------------------------------------------------- SQL, NoSQL and PostgreSQL


def test_sql_and_nosql(taxonomy):
    found = tags("Comfortable with SQL/NoSQL stores", taxonomy)
    assert "SQL" in found


def test_nosql_alone_is_not_sql(taxonomy):
    assert "SQL" not in tags("Experience with NoSQL databases.", taxonomy)


def test_postgresql_does_not_count_as_sql(taxonomy):
    # Design choice: we count only what the post says. No inference.
    found = tags("We run PostgreSQL on AWS.", taxonomy)
    assert "PostgreSQL" in found
    assert "SQL" not in found


def test_postgres_short_name(taxonomy):
    assert "PostgreSQL" in tags("Rails and Postgres shop", taxonomy)


def test_sql_variants(taxonomy):
    assert "SQL" in tags("Strong T-SQL and stored procedures.", taxonomy)
    assert "SQL" in tags("Write SQL every day.", taxonomy)
    assert "SQL" not in tags("MySQL and SQLite", taxonomy)


# ---------------------------------------------------------------------- AI

ML_AI = "Machine Learning / AI"


@pytest.mark.parametrize(
    "text",
    [
        "We maintain our servers in Hawaii.",
        "Based in Dubai, we maintain a legal tech platform.",
        "Our Thai team will train new hires.",
        "Ukraine-based, we paint, braid and chain.",
    ],
)
def test_ai_not_inside_words(text, taxonomy):
    assert ML_AI not in tags(text, taxonomy)


@pytest.mark.parametrize(
    "text",
    [
        "We build AI products for banks.",
        "AI/ML engineer wanted",
        "Strong machine learning background",
        "ML and deep learning experience",
        "AI-powered search",
    ],
)
def test_ai_positive(text, taxonomy):
    assert ML_AI in tags(text, taxonomy)


# --------------------------------------------------------------- LLM forms


@pytest.mark.parametrize(
    "text",
    [
        "Build products on LLMs.",
        "We fine-tune large language models.",
        "Experience with GenAI is a plus.",
        "Generative AI team lead",
        "LLM-powered agents",
        "Hands-on with ChatGPT APIs.",
    ],
)
def test_llm_forms(text, taxonomy):
    assert "LLM / GenAI" in tags(text, taxonomy)


def test_generative_ai_is_not_also_ml_ai(taxonomy):
    found = tags("We are a Generative AI startup.", taxonomy)
    assert "LLM / GenAI" in found
    assert ML_AI not in found


def test_llm_negative(taxonomy):
    assert "LLM / GenAI" not in tags("She has an LL.M. degree.", taxonomy)


# --------------------------------------------------- Other ambiguous names


def test_dbt_vs_dbt_therapy(taxonomy):
    assert "dbt" in tags("Snowflake, dbt and Airflow", taxonomy)
    assert "dbt" not in tags("Therapists trained in DBT and CBT.", taxonomy)


def test_snowflake_company_vs_schema(taxonomy):
    assert "Snowflake" in tags("Our warehouse is Snowflake.", taxonomy)
    assert "Snowflake" not in tags("Model data as a snowflake schema.", taxonomy)
    assert "Snowflake" not in tags("Nobody is a special snowflake.", taxonomy)


def test_rag_vs_rag_status(taxonomy):
    assert "RAG" in tags("Build RAG pipelines over internal docs.", taxonomy)
    assert "RAG" in tags("Retrieval-Augmented Generation experience", taxonomy)
    assert "RAG" not in tags("Weekly RAG status report to the PMO.", taxonomy)


def test_angularjs_vs_angular(taxonomy):
    assert "AngularJS" in tags("Maintain a legacy AngularJS app.", taxonomy)
    assert "AngularJS" in tags("Angular 1.x codebase", taxonomy)
    assert "AngularJS" not in tags("Modern Angular 14 and RxJS", taxonomy)


def test_kubernetes_forms(taxonomy):
    assert "Kubernetes" in tags("We run k8s on GCP.", taxonomy)
    assert {"Kubernetes", "GCP"} <= tags("We run k8s on GCP.", taxonomy)


def test_vector_database_forms(taxonomy):
    assert "Vector Databases" in tags("Experience with pgvector or Pinecone", taxonomy)
    assert "Vector Databases" in tags("Own our vector search stack.", taxonomy)


def test_azure_company_not_colour(taxonomy):
    assert "Azure" in tags("Deploy on Azure.", taxonomy)
    assert "Azure" not in tags("The azure sky was clear.", taxonomy)


# ------------------------------------------------------------ HTML handling


def test_clean_text_strips_tags_and_decodes_entities():
    cleaned = clean_text("<p>We use <i>Go</i> &amp; Rust&#x2F;C++</p>")
    assert "<" not in cleaned
    assert "We use" in cleaned
    assert "Go" in cleaned
    assert "& Rust/C++" in cleaned


def test_html_comment_is_tagged(taxonomy):
    html_post = (
        "Acme (YC W22) | Backend Engineer | Remote<p>"
        "Stack: Python, <i>Go</i> and PostgreSQL on AWS. "
        "Apply: <a href=\"https:&#x2F;&#x2F;acme.example&#x2F;jobs\">https:&#x2F;&#x2F;acme.example&#x2F;jobs</a>"
    )
    assert {"Python", "Go", "PostgreSQL", "AWS"} <= tags(html_post, taxonomy)


def test_encoded_slash_and_ampersand(taxonomy):
    assert {"C", "C++"} <= tags("Skills: C&#x2F;C++", taxonomy)
    assert "R" not in tags("Work in R&amp;D", taxonomy)


def test_urls_are_ignored(taxonomy):
    # The link text holds "golang" and "python", but they are not skills in the post.
    post = '<a href="https://golang.org/doc">https:&#x2F;&#x2F;golang.org&#x2F;doc&#x2F;python</a>'
    assert tags(post, taxonomy) == set()


def test_tag_attributes_do_not_leak(taxonomy):
    assert tags('<a href="https://x.example/react" class="Rust">here</a>', taxonomy) == set()


def test_literal_less_than_is_not_a_tag(taxonomy):
    # "&lt;3" is plain text. It must not swallow the text around it.
    assert {"Rust", "C++"} <= tags("I &lt;3 Rust and C++ &gt; Go-getters", taxonomy)


# ----------------------------------------------------------- full job post


def test_full_job_post(taxonomy):
    post = (
        "<p>Northwind Data | Senior Data Engineer | Remote (EU)</p>"
        "<p>Our stack: Python, SQL, dbt, Snowflake, Airflow, Spark and Kafka on AWS "
        "with Docker, Terraform and Kubernetes. We are adding RAG and LLM features. "
        "Series B. Our R&amp;D team is small. We want a Go-getter, not a go-to-market lead.</p>"
    )
    found = tags(post, taxonomy)
    expected = {
        "Python", "SQL", "dbt", "Snowflake", "Airflow", "Spark", "Kafka",
        "AWS", "Docker", "Terraform", "Kubernetes", "RAG", "LLM / GenAI",
    }
    assert found == expected
