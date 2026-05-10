from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from src.terminal_ui import TerminalUI


class TTYStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class TerminalUITests(unittest.TestCase):
    def test_width_respects_narrow_terminal(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        with patch("src.terminal_ui.shutil.get_terminal_size", return_value=os.terminal_size((60, 20))):
            self.assertEqual(ui._width(), 60)

    def test_wrap_breaks_long_unspaced_tokens(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        text = "/this/is/a/very/long/path/" + ("a" * 180)
        wrapped = ui._wrap_preserving_paragraphs(text, 20)
        self.assertTrue(wrapped)
        self.assertTrue(all(ui._display_width(line) <= 20 for line in wrapped))

    def test_wrap_respects_wide_characters(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        wrapped = ui._wrap_preserving_paragraphs("这是一个很长的中文说明没有空格但是不能超出边框", 12)
        self.assertTrue(wrapped)
        self.assertTrue(all(ui._display_width(line) <= 12 for line in wrapped))

    def test_panel_keeps_colored_frame_on_body_rows(self) -> None:
        output_stream = TTYStringIO()
        ui = TerminalUI(output_stream=output_stream, input_stream=io.StringIO())
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            ui.panel("Title", ["Body text"], color=ui.FG_BLUE)

        rendered = output_stream.getvalue()
        self.assertIn(f"{ui.FG_BLUE}|{ui.RESET} Body text", rendered)

    def test_choose_action_uses_custom_input_stream(self) -> None:
        output_stream = io.StringIO()
        input_stream = io.StringIO("5\n")
        ui = TerminalUI(output_stream=output_stream, input_stream=input_stream)

        choice = ui.choose_action(["Refine A", "Refine B", "Refine C"])

        self.assertEqual(choice, "5")
        self.assertIn("Enter your choice:", output_stream.getvalue())

    def test_read_multiline_feedback_uses_custom_input_stream(self) -> None:
        ui = TerminalUI(
            output_stream=io.StringIO(),
            input_stream=io.StringIO("First line\nSecond line\n\n"),
        )

        feedback = ui.read_multiline_feedback()

        self.assertEqual(feedback, "First line\nSecond line")

    def test_intake_question_menu_supports_keyboard_selection(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        with (
            patch.object(ui, "_interactive_input_available", return_value=True),
            patch.object(ui, "_read_key", side_effect=["down", "enter"]),
        ):
            answer = ui.choose_intake_clarification_answer(
                "Which scope?",
                ["Small empirical study", "Full benchmark"],
                index=1,
                total=3,
            )

        self.assertEqual(answer, "Full benchmark")

    def test_intake_question_menu_is_not_cleared_after_answer(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        with (
            patch.object(ui, "_interactive_input_available", return_value=True),
            patch.object(ui, "_read_key", side_effect=["enter"]),
            patch.object(ui, "_clear_live_block", wraps=ui._clear_live_block) as clear_live_block,
        ):
            answer = ui.choose_intake_clarification_answer(
                "Which scope?",
                ["Small empirical study", "Full benchmark"],
                index=1,
                total=3,
            )

        self.assertEqual(answer, "Small empirical study")
        self.assertTrue(all(call.args[0] <= 0 for call in clear_live_block.call_args_list))

    def test_intake_custom_response_keeps_question_visible(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(output_stream=output, input_stream=io.StringIO("My custom scope\n"))
        with (
            patch.object(ui, "_interactive_input_available", return_value=True),
            patch.object(ui, "_read_key", side_effect=["down", "down", "enter"]),
        ):
            answer = ui.choose_intake_clarification_answer(
                "Which scope?",
                ["Small empirical study", "Full benchmark"],
                index=1,
                total=3,
            )

        self.assertEqual(answer, "My custom scope")
        rendered = output.getvalue()
        self.assertIn("Question: Which scope?", rendered)
        self.assertIn("Small empirical study", rendered)

    def test_intake_final_menu_supports_keyboard_selection(self) -> None:
        ui = TerminalUI(output_stream=io.StringIO(), input_stream=io.StringIO())
        with (
            patch.object(ui, "_interactive_input_available", return_value=True),
            patch.object(ui, "_read_key", side_effect=["down", "enter"]),
        ):
            choice = ui.choose_intake_final_action()

        self.assertEqual(choice, "5")


if __name__ == "__main__":
    unittest.main()
