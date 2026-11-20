"""Candidatura automática: currículo adaptado + carta + envio por e-mail.

Fluxo:
    radar (scrapers)  ->  vagas_vistas  ->  candidaturas (fila)
                                              |
            swipe (web) / auto (CLI)  ->  preparar (CV + carta + e-mail)
                                              |
                                           enviar (SMTP, com limites)
"""
