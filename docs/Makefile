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

html: conf.py instamatic.rst README.rst install.rst
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

README.rst: ../README.md
	pandoc --from=markdown --to=rst --output=README.rst ../README.md

instamatic.rst:
	$(SPHINXGEN) -eTf -t "$(TEMPLATESDIR)" -o "$(SOURCEDIR)" ../instamatic

examples.rst:
	$(PYTHON) make_examples.py $(notebooks)

install.rst:
	touch install.rst

clean:
	rm -rvf "$(BUILDDIR)" "$(STATICDIR)/examples" instamatic*.rst README.rst examples.*rst
	rm -rvf config.rst formats.rst gui.rst programs.rst setup.rst tem_api.rst tvips.rst
