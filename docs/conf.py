# Configuration file for the Sphinx documentation builder.

project = "pgwidgets-python"
copyright = "2024, PGWidgets Developers"
author = "PGWidgets Developers"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

# -- HTML output --
html_theme = "furo"
html_title = "pgwidgets-python"

# -- autodoc --
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# -- intersphinx --
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- napoleon --
napoleon_google_docstring = True
napoleon_numpy_docstring = True
