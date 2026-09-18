PYTHON ?= python3
SUBMAKE_PYTHON = $(if $(findstring /,$(PYTHON)),$(abspath $(PYTHON)),$(PYTHON))

.PHONY: all localizer optimizer verifier test
all: localizer optimizer verifier

localizer:
	$(MAKE) -C localizer

optimizer:
	$(MAKE) -C optimizer

verifier:
	$(MAKE) -C direct verify_big

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m unittest discover -s improvements/pipeline -p 'test_*.py'
	$(MAKE) -C localizer test PYTHON="$(SUBMAKE_PYTHON)"
	$(MAKE) -C optimizer test PYTHON="$(SUBMAKE_PYTHON)"
