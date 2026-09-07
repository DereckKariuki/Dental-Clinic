"""Prompt text in spec §6 (and the §5 LANGUAGE block) is a deliverable.

Project rule: if a change is needed, propose it in prompts/CHANGES.md — don't
silently rewrite it. These tests fail on any drift between the spec and the
prompt files, in either direction.
"""

import re

import pytest

FENCE = re.compile(r"^```\w*\n(.*?)^```", re.M | re.S)

# Blocks the spec hands over as prompt text, and where each must appear.
REQUIRED_BLOCKS = {
    "LANGUAGE": ["voice_agent.md"],
    "=== PRICING": ["voice_agent.md", "whatsapp_agent.md"],
    "=== PAYMENT AND COVER": ["voice_agent.md", "whatsapp_agent.md"],
    "=== EMERGENCY": ["voice_agent.md"],
    "=== IDENTITY DISCLOSURE": ["voice_agent.md", "whatsapp_agent.md"],
    "=== FAQ HANDLING": ["voice_agent.md", "whatsapp_agent.md"],
}


def _blocks(text):
    return [m.group(1).rstrip("\n") for m in FENCE.finditer(text)]


@pytest.fixture(scope="module")
def spec_blocks(pytestconfig):
    root = pytestconfig.rootpath
    text = (root / "docs" / "build-pack-kenya.md").read_text(encoding="utf-8")
    out = {}
    for block in _blocks(text):
        for key in REQUIRED_BLOCKS:
            if block.startswith(key):
                out[key] = block
    return out


@pytest.fixture(scope="module")
def prompt_blocks(pytestconfig):
    root = pytestconfig.rootpath
    return {
        name: _blocks((root / "prompts" / name).read_text(encoding="utf-8"))
        for name in ("voice_agent.md", "whatsapp_agent.md")
    }


def test_spec_still_carries_every_prompt_block(spec_blocks):
    missing = set(REQUIRED_BLOCKS) - set(spec_blocks)
    assert not missing, f"spec §5/§6 no longer contains: {sorted(missing)}"


@pytest.mark.parametrize("key", sorted(REQUIRED_BLOCKS))
def test_prompt_files_reproduce_the_spec_block_verbatim(key, spec_blocks, prompt_blocks):
    expected = spec_blocks[key]
    for filename in REQUIRED_BLOCKS[key]:
        blocks = prompt_blocks[filename]
        candidates = [b for b in blocks if b.startswith(key)]
        assert candidates, f"{filename} is missing the {key} block"
        for got in candidates:
            assert got == expected, (
                f"{filename}: the {key} block has drifted from docs/build-pack-kenya.md.\n"
                "Prompt text in §6 is a deliverable — propose the change in "
                "prompts/CHANGES.md instead of editing it here.\n"
                f"--- spec ---\n{expected}\n--- prompt ---\n{got}"
            )


def test_whatsapp_prompt_has_no_language_handoff(prompt_blocks):
    """Spec §5: on WhatsApp code-switching is 'nearly a non-issue'."""
    joined = "\n".join(prompt_blocks["whatsapp_agent.md"])
    assert "LANGUAGE_HANDOFF" not in joined


def test_whatsapp_prompt_carries_the_emergency_wording(pytestconfig):
    """Spec §7: no emergency transfer on WhatsApp; this exact first message instead."""
    text = (pytestconfig.rootpath / "prompts" / "whatsapp_agent.md").read_text(encoding="utf-8")
    assert (
        "If this is urgent, please call us on [NUMBER] now, or go to casualty\n"
        "at [HOSPITAL]. I'll also flag this for the team." in text
    )


def test_unresolved_first_pack_blocks_are_declared_not_invented(pytestconfig):
    """The first build pack is not in this repo. The gap must stay visible."""
    for name in ("voice_agent.md", "whatsapp_agent.md"):
        text = (pytestconfig.rootpath / "prompts" / name).read_text(encoding="utf-8")
        assert "unresolved" in text.lower(), f"{name} no longer flags the first-pack gap"
