"""Small editable examples compiled to the existing Flow IR, not executable code."""

from __future__ import annotations

from typing import Any


def browser_workflow(url: str, *, headless: bool = True) -> dict[str, Any]:
    def step(
        name: str, operation: str, args: dict[str, Any], field: str, value: Any
    ) -> dict[str, Any]:
        return {
            "id": name,
            "intent": name.replace("_", " "),
            "action": "wait",
            "api_binding": {
                "kind": "tool",
                "url_template": "browser",
                "method": operation,
                "on_unavailable": "halt",
                "body_template": args,
                "effects": [
                    {
                        "kind": "field_equals",
                        "match": {"provider": "browser"},
                        "field": field,
                        "value": value,
                        "timeout_s": 3,
                    }
                ],
            },
        }

    return {
        "schema_version": "l1ght5p33d/v1",
        "id": "poster-demo",
        "description": "Create and save a poster in a harmless local browser fixture.",
        "application": "browser",
        "configuration": {
            "url": url,
            "title_pattern": "L1ght5p33d Poster Studio",
            "headless": headless,
        },
        "workflow": {
            "schema_version": 2,
            "name": "Poster Studio",
            "params": {"title": "Make something wonderful"},
            "steps": [
                step(
                    "name_poster",
                    "fill",
                    {
                        "selectors": [{"kind": "label", "name": "Poster title"}],
                        "text": "{title}",
                    },
                    "poster_title",
                    {"param": "title"},
                ),
                step(
                    "choose_palette",
                    "select",
                    {
                        "selectors": [{"kind": "label", "name": "Palette"}],
                        "label": "Sunset",
                    },
                    "palette",
                    "Sunset",
                ),
                step(
                    "save_poster",
                    "click",
                    {
                        "selectors": [
                            {
                                "kind": "role",
                                "role": "button",
                                "name": "Old save label",
                            },
                            {"kind": "role", "role": "button", "name": "Save poster"},
                        ]
                    },
                    "saved",
                    "Saved",
                ),
            ],
        },
    }
