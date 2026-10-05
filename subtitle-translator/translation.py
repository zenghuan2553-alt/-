"""Reuse Whisper's CTranslate2 runtime for offline English → Simplified Chinese."""
from pathlib import Path

import ctranslate2
import sentencepiece


class ChineseTranslator:
    def __init__(self, folder):
        folder = Path(folder)
        self.source = sentencepiece.SentencePieceProcessor(model_file=str(folder / "source.spm"))
        self.target = sentencepiece.SentencePieceProcessor(model_file=str(folder / "target.spm"))
        self.model = ctranslate2.Translator(str(folder), device="cpu", compute_type="int8", intra_threads=4)

    def translate(self, text):
        tokens = [">>cmn_Hans<<"] + self.source.encode(text, out_type=str) + ["</s>"]
        result = self.model.translate_batch([tokens], beam_size=2, max_decoding_length=192)[0]
        return self.target.decode([token for token in result.hypotheses[0] if token not in {"</s>", ">>cmn_Hans<<"}])
