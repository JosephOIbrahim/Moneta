#!/usr/bin/env bash
# =============================================================================
# NotebookLM Video Generator — Moneta Explainer
# =============================================================================
# Creates a cinematic whiteboard-style video explaining Moneta in layman's terms.
#
# Prerequisites:
#   1. pip install notebooklm-py
#   2. notebooklm login   (must succeed — fix Playwright first if needed)
#   3. Run this script from the Moneta repo root
#
# Usage:
#   bash scripts/notebooklm_video.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/outputs"
mkdir -p "$OUTPUT_DIR"

echo "=== Mile 1 of ~6: Creating notebook ==="
NB_JSON=$(notebooklm create "Moneta — How AI Memory Works" --json)
NB_ID=$(echo "$NB_JSON" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Notebook created: $NB_ID"

notebooklm use "$NB_ID"

echo "=== Mile 2 of ~6: Adding source documents ==="

# Add the three key docs that explain Moneta at different levels
SRC1_JSON=$(notebooklm source add "$REPO_ROOT/README.md" --json 2>&1) || true
echo "  Added README.md"

SRC2_JSON=$(notebooklm source add "$REPO_ROOT/MONETA.md" --json 2>&1) || true
echo "  Added MONETA.md"

SRC3_JSON=$(notebooklm source add "$REPO_ROOT/ARCHITECTURE.md" --json 2>&1) || true
echo "  Added ARCHITECTURE.md"

SRC4_JSON=$(notebooklm source add "$REPO_ROOT/docs/phase3-closure.md" --json 2>&1) || true
echo "  Added phase3-closure.md"

echo "=== Mile 3 of ~6: Waiting for source indexing ==="
# Give sources time to process (30-60s each typically)
sleep 10
echo "  Checking source status..."

MAX_WAIT=300
ELAPSED=0
while true; do
    STATUS=$(notebooklm source list --json 2>&1)
    PROCESSING=$(echo "$STATUS" | python -c "
import sys, json
data = json.load(sys.stdin)
sources = data.get('sources', [])
pending = [s for s in sources if s.get('status','') != 'ready']
print(len(pending))
" 2>/dev/null || echo "?")

    if [ "$PROCESSING" = "0" ]; then
        echo "  All sources ready!"
        break
    fi

    ELAPSED=$((ELAPSED + 15))
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "  WARNING: Timed out waiting for sources. Proceeding anyway..."
        break
    fi

    echo "  Still processing ($PROCESSING sources remaining)... waiting 15s"
    sleep 15
done

echo "=== Mile 4 of ~6: Generating cinematic video ==="
# Whiteboard style = line art drawing aesthetic
# Explainer format = cinematic narration

VIDEO_INSTRUCTIONS="$(cat <<'PROMPT'
Create a cinematic explainer video about Moneta — a memory system for AI agents.

TARGET AUDIENCE: Complete beginners. No programming knowledge assumed.

NARRATIVE ARC — tell it as a story:

1. OPEN with the human problem: "How do you remember things? Your brain doesn't store
   memories like files on a computer. It strengthens what matters and lets the rest fade.
   What if AI could work the same way?"

2. INTRODUCE MONETA: Named after the Roman goddess of memory and warning — her temple
   housed the Roman mint because she reminded people what was valuable. Moneta does the
   same thing for AI: it reminds agents what matters.

3. THE HOT TIER — Working Memory: Like your desk. Things you're actively using sit right
   here. Fast to grab, but limited space. In Moneta, this is the ECS — a lightning-fast
   in-memory system where active memories live.

4. THE DECAY — Forgetting on Purpose: Every memory has a "utility score" that naturally
   fades over time — like how you forget what you had for lunch last Tuesday. But if
   something keeps coming up (the agent keeps using it), its score stays high. The math
   is beautiful: exponential decay with a 6-hour half-life. Unused memories fade.
   Important ones persist.

5. THE ATTENTION SIGNAL — "Pay attention to this!": Agents can flag certain memories as
   important — like highlighting text in a book. These attention signals protect memories
   from fading too quickly.

6. THE SLEEP PASS — Consolidation: Just like how your brain consolidates memories during
   sleep, Moneta has a "sleep pass." It looks at everything on the desk, decides what's
   worth keeping long-term, and writes it to the Cold Tier. Low-utility, rarely-accessed
   memories get pruned. Valuable ones get preserved.

7. THE COLD TIER — Long-Term Memory (OpenUSD): Here's where it gets clever. Long-term
   memories are stored using OpenUSD — the same technology Pixar uses to build animated
   movies. Why? Because USD is built for composing complex scenes from layers — and
   that's exactly what memory is. Each day's memories become a new layer. Protected
   memories sit in a special reinforced layer that can never be overwritten.

8. THE FOUR OPERATIONS — Beautifully Simple: The entire system exposes just four
   operations to the AI agent: deposit a memory, query memories, signal attention,
   and get a consolidation manifest. The agent never needs to know about USD, decay
   math, or any internals. It just remembers.

9. CLOSE with the vision: "Moneta is the foundation. One project handles memory.
   Its sibling Octavius handles coordination. Together, they give AI agents something
   they've never had before — a real cognitive substrate. Not a database. A mind."

TONE: Warm, cinematic, awe-inspiring. Think Kurzgesagt meets a TED talk.
Keep it accessible. Zero jargon without explanation.
PROMPT
)"

notebooklm generate video \
    "$VIDEO_INSTRUCTIONS" \
    --style whiteboard \
    --format explainer \
    --json \
    2>&1 | tee "$OUTPUT_DIR/video_task.json"

TASK_ID=$(python -c "
import sys, json
data = json.load(open('$OUTPUT_DIR/video_task.json'))
print(data.get('task_id', data.get('id', 'unknown')))
" 2>/dev/null || echo "unknown")

echo ""
echo "=== Mile 5 of ~6: Video generation started ==="
echo "  Task ID: $TASK_ID"
echo "  Notebook ID: $NB_ID"
echo "  Style: whiteboard (line art drawing)"
echo "  Format: explainer (cinematic)"
echo ""
echo "  Video generation typically takes 15-45 minutes."
echo "  Check status with:  notebooklm artifact list"
echo ""

echo "=== Mile 6 of ~6: Waiting for video completion ==="
echo "  (Will wait up to 45 minutes — Ctrl+C to skip and check manually later)"
echo ""

if notebooklm artifact wait "$TASK_ID" --timeout 2700 2>&1; then
    echo ""
    echo "  Video complete! Downloading..."
    notebooklm download video "$OUTPUT_DIR/moneta_explainer.mp4"
    echo ""
    echo "============================================"
    echo "  DONE! Video saved to:"
    echo "  $OUTPUT_DIR/moneta_explainer.mp4"
    echo "============================================"
else
    echo ""
    echo "  Video still processing or timed out."
    echo "  Check status:   notebooklm artifact list"
    echo "  Download later:  notebooklm download video $OUTPUT_DIR/moneta_explainer.mp4"
fi
