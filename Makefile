.PHONY: all sync validate test typecheck privacy-gate check-placeholders check-claims demo video

all: validate

sync:
	uv sync

validate: typecheck test privacy-gate check-placeholders check-claims

test:
	@if [ ! -d src ]; then echo "skipping test: src/ absent"; exit 0; fi
	uv run pytest -q

typecheck:
	@if [ ! -d src ]; then echo "skipping typecheck: src/ absent"; exit 0; fi
	uv run mypy src/sonar

privacy-gate:
	uv run python scripts/privacy_gate.py

check-placeholders:
	uv run python scripts/check_placeholders.py

check-claims:
	uv run pytest -rsx -v tests/test_published_claims.py

demo:
	uv run sonar run --fixtures --profile smoke Nubank --out out/repro
	uv run sonar render --from out/repro | head -3

video:
	cd video && pnpm lint && pnpm collect && pnpm shots && pnpm render && pnpm srt && pnpm cuts && pnpm still:social
	mkdir -p results/video && cp video/out/sonar.mp4 video/out/sonar.srt video/out/cuts.png results/video/
