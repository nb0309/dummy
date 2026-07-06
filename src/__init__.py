"""Modular, skill-based WCAG accessibility classifier.

Each WCAG success criterion (and, for 1.3.1, each technique family) is described
by a self-contained *skill* spec under ``src/skills``. For a given captured DOM
element a lightweight router selects the applicable skills, an evidence block is
built from the rich capture columns, and a single structured LLM call decides
whether the element is accessible.

See ``src/run.py`` for the entrypoint and the approved plan for background.
"""
