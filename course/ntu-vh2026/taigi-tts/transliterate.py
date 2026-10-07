"""JSON stdin/stdout bridge: Taiwanese Han characters to citation-tone POJ.

This is transliteration, not Mandarin-to-Taiwanese translation.
Exit 0 means conversion completed. Exit 2 reports invalid or uncovered text.
"""
import importlib.metadata
import json
import sys
import unicodedata

from taibun import Converter


def is_han(char):
    name = unicodedata.name(char, "")
    return "CJK" in name and "IDEOGRAPH" in name


def main():
    try:
        payload = json.load(sys.stdin)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if len(text) > 400:
            raise ValueError("text exceeds the 400-character limit. Split at sentence boundaries")
        if not any(is_han(char) for char in text):
            raise ValueError("taigi-hanzi requires Taiwanese Han characters. Use the POJ endpoint for romanized input")
        unsupported = sorted(set(char for char in text if char.isdigit() or "LATIN" in unicodedata.name(char, "")))
        if unsupported:
            raise ValueError("Write digits and foreign terms in Taiwanese Han characters before synthesis: " + " ".join(unsupported))
        converter = Converter(system="POJ", dialect="south", format="mark", sandhi="none")
        poj = converter.get(text.strip())
        remaining = sorted(set(char for char in poj if is_han(char)))
        if remaining:
            raise ValueError("Taibun has no conversion for these Han characters: " + " ".join(remaining))
        if not poj or not any(char.isalpha() for char in poj):
            raise ValueError("No pronounceable POJ was generated")
        result = {
            "ok": True, "text": text.strip(), "poj": poj,
            "taibun_version": importlib.metadata.version("taibun"),
            "system": "POJ", "dialect": "south", "sandhi": "none",
            "translation_performed": False,
        }
    except (ValueError, TypeError, AttributeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
