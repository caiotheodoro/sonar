.PHONY: all sync validate test typecheck privacy-gate check-placeholders check-claims demo video

all: validate

sync:
	uv sync

validate: privacy-gate check-placeholders check-claims

test:
	@if [ ! -d src ]; then echo "skipping test: src/ absent"; exit 0; fi
	pytest

typecheck:
	@if [ ! -d src ]; then echo "skipping typecheck: src/ absent"; exit 0; fi
	mypy src/sonar

privacy-gate:
	python scripts/privacy_gate.py

check-placeholders:
	python scripts/check_placeholders.py

check-claims:
	uv run pytest -rsx -v tests/test_published_claims.py

demo:
	@echo "demo: pending pipeline"

video:
	cd video && pnpm lint && pnpm collect && pnpm shots && pnpm render && pnpm srt
