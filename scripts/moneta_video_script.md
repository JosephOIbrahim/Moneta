# Moneta: How AI Memory Actually Works
## A Layman's Guide — Video Script Source

---

### THE HOOK

Right now, every AI you talk to has amnesia.

You tell ChatGPT your name. You explain your job. You share your preferences. And the next day? Gone. Every conversation starts from scratch. AI doesn't remember — it pretends to, by re-reading old chat logs. That's not memory. That's a filing cabinet.

Your brain doesn't work like a filing cabinet. And neither does Moneta.

---

### WHAT IS MONETA?

Moneta is a memory system for AI agents. Not a chatbot feature. Not a database with a search bar. An actual working memory — one that strengthens what matters and lets the rest fade, the same way your brain does.

The name comes from Juno Moneta, the Roman goddess of memory and warning. Her temple in ancient Rome also housed the mint — because she reminded people what was valuable. That's what this system does. It reminds AI what's valuable.

---

### THE DESK AND THE ARCHIVE — Two Tiers of Memory

Think about how you work at a desk.

**Your desk** has the stuff you're actively using right now. Notes, documents, your phone, a coffee cup. It's fast to grab anything on your desk, but space is limited. You can't keep everything there forever.

**Your archive** is the filing room down the hall. Important things you finished with get filed away there. Organized, durable, retrievable — but you have to go get them.

Moneta works exactly the same way.

**The Hot Tier** is the desk. It's a fast in-memory system where active memories live. When the AI deposits a new memory or looks something up, it happens here. Instant.

**The Cold Tier** is the archive. It uses a technology called OpenUSD — the same system that Pixar uses to build animated movies like Toy Story and Finding Nemo. More on why that matters in a moment.

---

### FORGETTING ON PURPOSE — Why Decay Is a Feature

Here's something counterintuitive: a good memory system needs to forget.

Your brain does this naturally. You remember what you had for breakfast this morning, but probably not what you had three Tuesdays ago. Unless something made that Tuesday special — a birthday, a bad meal, a great conversation. Then it sticks.

Moneta copies this with a concept called **exponential decay**. Every memory starts with a utility score of 1.0 — full strength. Over time, that score naturally fades. After 6 hours with no reinforcement, a memory drops to half strength. After 24 hours, it's down to about 6% — nearly gone.

But here's the key: if the AI keeps using a memory — keeps coming back to it — the score stays high. Important memories survive. Forgotten ones fade. No one has to manually decide what to keep. The math handles it.

---

### THE ATTENTION SIGNAL — "This Matters"

Sometimes the AI wants to say "hey, pay attention to this one."

Maybe a user just said something important. Maybe a fact keeps coming up across different conversations. The AI can send an **attention signal** — a boost that raises a memory's utility score and marks it as "attended to."

Think of it like highlighting a sentence in a textbook. You're not changing the words. You're marking it as worth remembering.

Memories that get highlighted a lot are almost impossible to forget. Memories that never get highlighted? They fade naturally.

---

### THE SLEEP PASS — When the Brain Tidies Up

You know how sleep is when your brain actually consolidates memories? During the day you collect experiences, and at night your brain sorts through them — strengthening the important stuff, discarding the noise.

Moneta has a **sleep pass** that does the same thing.

When the system gets too full, or when there's a quiet moment with no active work, the sleep pass kicks in. It looks at every memory on the desk and asks two questions:

1. **Is this memory fading and rarely used?** (Low utility, low attention count) — If yes: **delete it.** It wasn't important.

2. **Is this memory fading but has been useful before?** (Low utility, but it's been attended to multiple times) — If yes: **move it to the archive.** It earned long-term storage.

Everything else stays on the desk for now.

This is not a cron job running every 5 minutes. It only happens when there's a reason — the desk is overflowing, or the AI has a quiet moment. Efficient, not wasteful.

---

### THE PIXAR CONNECTION — Why OpenUSD?

This is where it gets clever.

OpenUSD (Universal Scene Description) was invented by Pixar to manage impossibly complex animated movies. A single frame of a Pixar film might have millions of objects — characters, props, lights, textures — all built by different teams, all needing to work together seamlessly.

USD solves this with **layers and composition**. Different teams work on different layers. The system knows how to stack them together, with rules about which layer wins when there's a conflict. Stronger layers override weaker ones. It's like a stack of transparencies — you see through to whatever layer has the answer.

Moneta uses this same layering system for memory — but instead of 3D objects, the layers hold memories.

**Each day's memories become a new layer** — like a new page in a journal. Today's memories sit on top. Yesterday's sit below. Last week's sit further down.

**Protected memories get a special reinforced layer** — pinned to the very bottom of the stack in the strongest position. These are memories that can never be overwritten, never decay. The AI equivalent of your childhood home address or your mother's name.

**When a memory fades from full detail to a summary** — like how you remember "I went to a great restaurant in Brooklyn" but not every dish you ordered — that transition happens through USD's variant system. The full detail and the summary both exist. The system picks whichever version is most appropriate.

None of this requires the AI to understand any of it. The composition engine handles everything automatically.

---

### THE FOUR OPERATIONS — Beautifully Simple

The entire system — all the decay math, the attention signals, the sleep passes, the USD layers, the consolidation — is hidden behind exactly four operations:

1. **Deposit** — Store a memory. ("The user prefers short answers.")
2. **Query** — Find relevant memories. ("What do I know about this user?")
3. **Signal Attention** — Mark something as important. ("That preference keeps coming up.")
4. **Get Consolidation Manifest** — See what moved to long-term storage. ("What got archived last night?")

That's it. Four operations. The AI agent never sees USD. Never touches decay math. Never manages layers. It deposits, queries, signals, and checks the manifest. Everything else is substrate.

This is a deliberate design choice. The fewer things an agent needs to understand, the fewer things it can break.

---

### WHY THIS MATTERS

Every major AI company is working on memory. Mem0, Letta, Zep, HippoRAG — they all use databases and vector stores. Good tools, proven tech.

Moneta uses none of them as its core substrate. It uses a composition engine designed for spatial storytelling. That's a fundamentally different bet.

The bet is this: memory isn't a retrieval problem. It's a composition problem. Memories don't exist in isolation — they overlap, conflict, reinforce, fade, and compose into understanding. A system designed for composition handles that natively. A database needs to fake it.

Moneta is the memory half. Its sibling project, Octavius, handles coordination — how multiple agents work together on a shared stage. Same USD foundation. Same layering principles. Together, they form a cognitive substrate: not a database with AI on top, but a mind-like foundation that AI agents live inside.

---

### THE ROAD HERE

Moneta was built in three phases across months of rigorous engineering:

**Phase 1** built the hot tier — the desk. The fast in-memory system, the four-operation API, the decay math, the attention signals, the sleep pass. 94 tests. All green.

**Phase 2** was the benchmark. Before connecting to USD, the team ran 243 different configurations to measure exactly how fast (or slow) USD operations would be under realistic load. The result: within a carefully defined operating envelope, USD performs well. Outside it, it degrades gracefully.

**Phase 3** connected the real USD engine. The archive went live. Memories flow from the desk to Pixar's composition engine and back. The final safety verification ran 775 million assertions across 10,000 iterations with zero failures.

Version 1.0 shipped.

---

### VIDEO GENERATION INSTRUCTIONS

This source document is written for NotebookLM video generation. When creating the video:

- **Style:** Use a line art / whiteboard drawing style. Think hand-drawn diagrams appearing as the narrator explains each concept. Clean, minimal, cinematic.
- **Tone:** Warm, confident, awe-inspiring. The narrator should sound like they're sharing something genuinely exciting — because it is.
- **Pacing:** ADHD-friendly. Short segments. Each concept gets its own visual beat. Never linger. Always moving forward.
- **Metaphors are primary.** The desk. The archive. Highlighting text. Sleep. Pixar. These are the visual anchors. Draw them.
- **No code.** No technical diagrams. No architecture boxes. If something needs explaining, use the metaphor, not the implementation.
- **The Roman goddess opening** should feel cinematic — a temple, a mint, a goddess who reminds you what's valuable.
- **The Pixar connection** should feel like a reveal — "the same technology that built Toy Story now powers AI memory."
- **Close with forward motion.** Not "this is done" but "this is the foundation for what comes next."
