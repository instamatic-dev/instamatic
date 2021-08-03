# Minimal makefile for Sphinx documentation
#
# You can set these variables from the command line.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SPHINXGEN     ?= sphinx-apidoc
SPHINXPROJ    = instamatic
PYTHON        ?= python
PIP           ?= pip
SOURCEDIR     = .
BUILDDIR      = _build
TEMPLATESDIR  = _templates
STATICDIR     = _static

html: conf.py instamatic.rst readme.rst install.rst
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

readme.rst: ../readme.md
	pandoc --from=markdown --to=rst --output=readme.rst ../readme.md

instamatic.rst:
	$(SPHINXGEN) -eTf -t "$(TEMPLATESDIR)" -o "$(SOURCEDIR)" ../instamatic

examples.rst:
	$(PYTHON) make_examples.py $(notebooks)

install.rst:
	touch install.rst

clean:
	rm -rvf "$(BUILDDIR)" "$(STATICDIR)/examples" instamatic*.rst readme.rst examples.*rst
	rm -rvf config.rst formats.rst gui.rst programs.rst setup.rst tem_api.rst tvips.rst
