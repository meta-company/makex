# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import os
from datetime import datetime

project = 'makex'
copyright = f'{datetime.now().year} Makex Authors'
author = "Makex Authors"

# The full version, including alpha/beta/rc tags
release = os.environ.get("RELEASE", "")

# The short X.Y version
version = os.environ.get("VERSION", "")

# Change this to modify the prefix.
html_baseurl = '/makex/latest/'

nitpick_ignore = [
    ('py:class', 'PathLike'),
    ('py:class', 'string'),
    ('py:class', 'PathLike'),
]

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
import sys
from pathlib import Path

PYTHON_PATH = Path(__file__)
source = PYTHON_PATH.resolve().parent.parent.parent.joinpath("python").as_posix()

sys.path.append(source)
sys.path.insert(0, Path('.').absolute().as_posix())

# -- General configuration ---------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
# needs_sphinx = '1.0'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path .
exclude_patterns = ['_build', '_templates']

AUTOSUMMARY = False
AUTODOC = True
MYST = True
INTERSPHINX = True
AUTOPROGRAM = True
NOTFOUND = True

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ["sphinx.ext.viewcode", "sphinx.ext.todo"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = {
    '.rst': 'restructuredtext',
    '.txt': 'markdown',
    '.md': 'markdown',
}

# The master toctree document.
master_doc = 'index'

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = "en"

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# -- Options for HTML output -------------------------------------------------
## https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

import better

#html_logo = "path/to/myimage.png"

# -- Options for HTMLHelp output ---------------------------------------------

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The theme to use for HTML and HTML Help pages.
#html_theme = 'alabaster'
html_theme = "better"
html_theme_path = [better.better_theme_path]
html_show_sourcelink = True

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
html_css_files = [
    'custom.css',
]
html_copy_source = True
html_last_updated_fmt = ""

# Output file base name for HTML help builder.
htmlhelp_basename = 'makexdoc'
html_show_sphinx = False
html_title = "Makex Documentation"

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# The default sidebars (for documents that don't match any pattern) are
# defined by theme itself.  Builtin themes are using these templates by
# default: ``['localtoc.html', 'relations.html', 'sourcelink.html',
# 'searchbox.html']``
html_sidebars = {
    '**': [
        'indexsidebar.html',
        'localtoc.html',
        'searchbox.html',
        'sidebarhelp.html',
        'sourcelink.html',
    ],
    'index': ['indexsidebar.html', 'searchbox.html', 'sidebarhelp.html', 'sourcelink.html'],
}

# Theme options are theme-specific and customize the look and feel of a theme
# further.
# For a list of options available for each theme, see the documentation.
# yapf: disable
html_theme_options = {

    # show sidebar on the right instead of on the left
    'rightsidebar': False,

    # inline CSS to insert into the page if you're too lazy to make a
    # separate file
    'inlinecss': '',

    # CSS files to include after all other CSS files
    # (refer to by relative path from conf.py directory, or link to a
    # remote file)
    #'cssfiles': ['_static/custom.css'], # default is empty list

    # show a big text header with the value of html_title
    'showheader': True,

    # show the breadcrumbs and index|next|previous links at the top of
    # the page
    'showrelbartop': True, # same for bottom of the page
    'showrelbarbottom': True,

    # show the self-serving link in the footer
    'linktotheme': False,

    # width of the sidebar. page width is determined by a CSS rule.
    # I prefer to define things in rem because it scales with the
    # global font size rather than pixels or the local font size.
    'sidebarwidth': '15rem',

    # color of all body text
    'textcolor': '#000000',

    # color of all headings (<h1> tags); defaults to the value of
    # textcolor, which is why it's defined here at all.
    'headtextcolor': '',

    # color of text in the footer, including links; defaults to the
    # value of textcolor
    'footertextcolor': '',

    # Google Analytics info
    'ga_ua': '',
    'ga_domain': '',
}
# yapf: enable

# -- Options for LaTeX output ------------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'makex.tex', 'makex Documentation', 'nate skulic', 'manual'),
]

# -- Options for manual page output ------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [(master_doc, 'makex', 'makex Documentation', [author], 1)]

# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        master_doc,
        'makex',
        'makex Documentation',
        author,
        'makex',
        'One line description of project.',
        'Miscellaneous'
    ),
]

# Warn about all refererences that are not found.
nitpicky = True

if MYST:
    extensions.append("myst_parser")

if AUTOSUMMARY:
    extensions.append('sphinx.ext.autosummary')
    autosummary_imported_members = False
    autosummary_generate = True

if AUTODOC:
    extensions.append("sphinx.ext.autodoc")
    autodoc_inherit_docstrings = False
    autodoc_preserve_defaults = True

if MYST:
    myst_enable_extensions = [
        "dollarmath",
        "amsmath",
        "deflist", # "html_admonition",
        # "html_image",
        "colon_fence", # "smartquotes",
        # "replacements",
        # "linkify",
        # "substitution",
    ]
    nb_execution_mode = "cache"

if INTERSPHINX:
    extensions.append("sphinx.ext.intersphinx")
    # Sphinx defaults to automatically resolve *unresolved* labels using all your Intersphinx mappings.
    # This behavior has unintended side effects, namely that documentations local references can
    # suddenly resolve to an external location.
    # See also:
    # https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#confval-intersphinx_disabled_reftypes
    #intersphinx_disabled_reftypes = ["*"]
    intersphinx_mapping = {
        "python": ("https://docs.python.org/3", None),
        "sphinx": ("https://www.sphinx-doc.org/en/master", None),
        "requests": ("https://docs.python-requests.org/en/latest/", None),
        #"pipx": ("https://pipx.pypa.io/stable/", None),
    }

if AUTOPROGRAM:

    def setup(app):
        autoprogram_setup(app)

    from autoprogram import setup as autoprogram_setup

if NOTFOUND:
    extensions.append("notfound.extension")
    notfound_template = "404.html"
    notfound_urls_prefix = html_baseurl
