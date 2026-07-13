"""Spanish rendering of the shared not-personalized-advice disclaimer.

Same product invariant as `disclaimer.NOT_PERSONALIZED_ADVICE_DISCLAIMER`, in the product's
default locale (`Settings.default_locale` is `es`). Kept as its own constant rather than
generated at runtime: compliance copy is reviewed text, not something to hand to a translator
model. Pick between the two with `disclaimer_for_locale`.
"""

NOT_PERSONALIZED_ADVICE_DISCLAIMER_ES = (
    "Este contenido es investigación de mercado con fines informativos; no constituye "
    "asesoramiento financiero, de inversión, legal ni fiscal personalizado, y no es una "
    "recomendación de compra, venta o mantenimiento de ningún instrumento. Consulta a un "
    "profesional autorizado antes de actuar en consecuencia."
)
