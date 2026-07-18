"""
Generate the bilingual thesis-guide PDFs (English + Arabic) served by the lab.

Arabic is shaped with arabic_reshaper + python-bidi and wrapped per visual line
so right-to-left line breaking is correct (reportlab alone does not bidi-wrap).
Output: static/thesis_guide_en.pdf, static/thesis_guide_ar.pdf
"""
from __future__ import annotations

from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE = Path(__file__).parent
STATIC = BASE / "static"

INK = (0.11, 0.09, 0.07)
CRIMSON = (0.64, 0.14, 0.19)
TEAL = (0.11, 0.37, 0.35)
FAINT = (0.42, 0.39, 0.34)

# Arial Unicode covers Arabic + Latin + digits + punctuation in one face,
# so mixed Arabic/Latin/number text (RC4, AES-256-GCM, 62%, …) renders cleanly.
pdfmetrics.registerFont(TTFont("Ar", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))

W, H = A4
ML, MR, MT, MB = 56, 56, 60, 56


class PDF:
    def __init__(self, path, rtl):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.rtl = rtl
        self.y = H - MT
        self.serif = "Ar" if rtl else "Times-Roman"
        self.bold = "Ar" if rtl else "Times-Bold"
        self.sans = "Ar" if rtl else "Helvetica"

    def _shape(self, t):
        return get_display(arabic_reshaper.reshape(t)) if self.rtl else t

    def _wrap(self, text, font, size, maxw):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            shaped = get_display(arabic_reshaper.reshape(trial)) if self.rtl else trial
            if pdfmetrics.stringWidth(shaped, font, size) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def _page_break(self, need):
        if self.y - need < MB:
            self.c.showPage()
            self.y = H - MT

    def para(self, text, size=11, font=None, color=INK, gap=6, lead=None, indent=0):
        font = font or self.serif
        lead = lead or size + 4
        maxw = W - ML - MR - indent
        for line in self._wrap(text, font, size, maxw):
            self._page_break(lead)
            shaped = self._shape(line)
            self.c.setFont(font, size)
            self.c.setFillColorRGB(*color)
            if self.rtl:
                self.c.drawRightString(W - MR, self.y, shaped)
            else:
                self.c.drawString(ML + indent, self.y, shaped)
            self.y -= lead
        self.y -= gap

    def bullet(self, text, size=11):
        mark = "•"
        maxw = W - ML - MR - 16
        lines = self._wrap(text, self.serif, size, maxw)
        for i, line in enumerate(lines):
            self._page_break(size + 4)
            shaped = self._shape(line)
            self.c.setFont(self.serif, size)
            self.c.setFillColorRGB(*INK)
            if self.rtl:
                if i == 0:
                    self.c.setFillColorRGB(*CRIMSON)
                    self.c.drawRightString(W - MR, self.y, mark)
                    self.c.setFillColorRGB(*INK)
                self.c.drawRightString(W - MR - 16, self.y, shaped)
            else:
                if i == 0:
                    self.c.setFillColorRGB(*CRIMSON)
                    self.c.drawString(ML, self.y, mark)
                    self.c.setFillColorRGB(*INK)
                self.c.drawString(ML + 16, self.y, shaped)
            self.y -= size + 4
        self.y -= 4

    def heading(self, text, size=16):
        self._page_break(size + 22)
        self.y -= 6
        shaped = self._shape(text)
        self.c.setFont(self.bold, size)
        self.c.setFillColorRGB(*CRIMSON)
        if self.rtl:
            self.c.drawRightString(W - MR, self.y, shaped)
        else:
            self.c.drawString(ML, self.y, shaped)
        self.y -= 4
        self.c.setStrokeColorRGB(*TEAL)
        self.c.setLineWidth(1.2)
        self.c.line(ML, self.y, W - MR, self.y)
        self.y -= 16

    def title_page(self, title, subtitle, tag):
        self.y = H - 200
        self.c.setFont(self.bold, 30)
        self.c.setFillColorRGB(*INK)
        for line in self._wrap(title, self.bold, 30, W - ML - MR):
            s = self._shape(line)
            (self.c.drawCentredString(W / 2, self.y, s))
            self.y -= 38
        self.y -= 10
        self.c.setFont(self.serif, 14)
        self.c.setFillColorRGB(*FAINT)
        for line in self._wrap(subtitle, self.serif, 14, W - ML - MR - 60):
            self.c.drawCentredString(W / 2, self.y, self._shape(line))
            self.y -= 20
        self.y -= 14
        self.c.setFont(self.sans, 10)
        self.c.setFillColorRGB(*TEAL)
        self.c.drawCentredString(W / 2, self.y, self._shape(tag))
        self.c.setStrokeColorRGB(*CRIMSON)
        self.c.setLineWidth(2)
        self.c.line(W / 2 - 80, H - 170, W / 2 + 80, H - 170)
        self.c.showPage()
        self.y = H - MT

    def save(self):
        self.c.save()


def build(rtl):
    d = "ar" if rtl else "en"
    p = PDF(STATIC / f"thesis_guide_{d}.pdf", rtl)

    if rtl:
        p.title_page(
            "المختبر التجريبي للقزحية والإخفاء",
            "دليل مبسّط لأطروحة الدكتوراه: اتصال خفيّ آمن مُفتَّح بالسمات الحيوية مع التحقق من صحة الرسائل",
            "دليل مرافق للموقع التجريبي المباشر")
        secs = [
            ("نظرة عامة", "para", [
                "تعالج هذه الأطروحة مشكلة الاتصال الخفيّ الآمن: كيف تُرسِل رسالة سرّية دون أن يعرف أحد بوجودها أصلاً، مع ضمان هوية المُرسِل وموثوقية الرسالة.",
                "يجمع النظام أربع تقنيات عادةً ما تُدرَس منفصلة: التعرّف على القزحية، وإخفاء المعلومات داخل الصور، والتشفير المُفتَّح بالسمة الحيوية، وتصنيف الرسائل الحقيقية والمزيّفة."]),
            ("المشكلة والفجوة البحثية", "para", [
                "الأنظمة السابقة تعالج كلاً من الإخفاء والتشفير وكشف الأخبار المزيّفة بمعزل عن بعضها.",
                "الفجوة: لا يوجد إطار موحّد يربط هوية المُرسِل (عبر القزحية) بمفتاح التشفير، ويتحقق من صحة الرسالة قبل إخفائها، ويدعم العربية والإنجليزية معًا."]),
            ("الإسهام", "bullets", [
                "توليد المفتاح من السمة الحيوية: مفتاح التشفير مشتقّ من قزحية المُرسِل بدلاً من كلمة مرور.",
                "قناة خفيّة متعددة الطبقات: إخفاء الرسالة، ثم تشفير الحامل، ثم تغليف المفتاح.",
                "بوابة موثوقية: مصنِّف يحكم على صحة الرسالة قبل إرسالها.",
                "دعم لغوي مزدوج: مصنِّف عربي إضافةً إلى الإنجليزي.",
                "تقييم تجريبي مقارن لعدة نماذج تعلّم آلي وعميق.",
                "تحديث أمني: وضع AES-256-GCM مع اشتقاق مفتاح PBKDF2 إلى جانب النسخة الأصلية."]),
            ("المسار خطوة بخطوة", "bullets", [
                "التعرّف على المُرسِل من قزحيته.",
                "التحقق من كون الرسالة حقيقية أم مزيّفة.",
                "إخفاء الرسالة داخل صورة عادية.",
                "تشفير الصورة بالمفتاح الحيوي (RC4 الأمين أو AES-GCM الآمن).",
                "إرسال الحزمة إلى المُستقبِل.",
                "فكّ التشفير واستخراج الرسالة والتحقق من سلامتها."]),
            ("مجموعات البيانات", "bullets", [
                "قاعدة قزحيات MMU: نحو 891 صورة لأعين 46 شخصًا (152 ميغابايت).",
                "مجموعة أخبار إنجليزية: 134 ألف صف مصنّفة حقيقية/مزيّفة (27 ميغابايت).",
                "مجموعة أخبار عربية: 4837 صفًا متوازنة تقريبًا.",
                "متجهات سمات القزحية (feat.csv) المستخدمة كمفاتيح تشفير."]),
            ("النتائج", "bullets", [
                "التعرّف على القزحية: دقة نحو 62% على 45 شخصًا (التخمين العشوائي ~2%).",
                "المصنِّف الإنجليزي: دقة نحو 92%.",
                "المصنِّف العربي: دقة نحو 88%."]),
            ("كيف تصل البيانات إلى الموقع", "para", [
                "البيانات الخام (3.9 غيغابايت) لا تُرفع إلى الموقع. يجري التدريب مرة واحدة على حاسوب الباحثة، وتُختصر المعرفة في ملفات نماذج صغيرة (نحو 12 ميغابايت).",
                "تُستورَد هذه النماذج إلى الموقع كما هي، فيجيب فورًا عند رفع صورة أو كتابة رسالة، دون الحاجة إلى البيانات الأصلية."]),
            ("كيفية الاستخدام", "para", [
                "افتحي الموقع، ثم اتبعي الخطوات من الأعلى إلى الأسفل: ارفعي قزحية، تحققي من الرسالة، أخفيها، شفّريها، أرسليها، ثم استقبليها. كل خطوة تعرض شرحًا وقياساتها، ويمكن تصدير سجل التجارب إلى ملف CSV للأطروحة."]),
        ]
    else:
        p.title_page(
            "The Iris-Stego Laboratory",
            "A plain-language guide to the PhD thesis: secure covert communication with biometric-derived keys and message-authenticity vetting",
            "Companion guide to the live experiment website")
        secs = [
            ("Overview", "para", [
                "This thesis addresses secure covert communication: how to send a secret message so that no one even suspects it exists, while binding the sender's identity and verifying the message is trustworthy.",
                "The system integrates four techniques usually studied separately: iris recognition, image steganography, biometric-keyed encryption, and real-vs-fake message classification."]),
            ("The Problem & Research Gap", "para", [
                "Prior systems treat steganography, encryption, and fake-news detection in isolation from one another.",
                "The gap: there is no unified framework that ties the sender's identity (via their iris) to the encryption key, vets the message's authenticity before hiding it, and does so bilingually (Arabic and English)."]),
            ("The Contribution", "bullets", [
                "Biometric-derived keying: the encryption key comes from the sender's iris, not a password.",
                "Multi-layer covert channel: hide the message, encrypt the carrier, then wrap the key.",
                "Authenticity gate: a classifier judges whether the message is genuine before it is sent.",
                "Bilingual scope: an Arabic classifier in addition to the English one.",
                "Comparative empirical evaluation across several ML and deep-learning models.",
                "Security upgrade: an AES-256-GCM mode with PBKDF2 key derivation alongside the faithful original."]),
            ("The Pipeline, Step by Step", "bullets", [
                "Identify the sender from their iris.",
                "Vet whether the message is authentic or fake.",
                "Hide the message inside an ordinary image.",
                "Encrypt the image with the biometric key (faithful RC4 or secure AES-GCM).",
                "Transmit the package to the receiver.",
                "Decrypt, extract the message, and verify integrity."]),
            ("The Datasets", "bullets", [
                "MMU Iris Database: ~891 eye images from 46 people (152 MB).",
                "English news dataset: 134,000 rows labelled real/fake (27 MB).",
                "Arabic news dataset: 4,837 near-balanced rows.",
                "Iris feature vectors (feat.csv) used as the encryption keys."]),
            ("Results", "bullets", [
                "Iris recognition: ~62% accuracy over 45 people (random guessing ~2%).",
                "English classifier: ~92% accuracy.",
                "Arabic classifier: ~88% accuracy."]),
            ("How the Data Reaches the Website", "para", [
                "The raw data (3.9 GB) is never uploaded to the website. Training runs once on the research PC, and the learned knowledge is distilled into small model files (~12 MB total).",
                "These models are imported into the website as-is, so it answers instantly when you upload an image or type a message, without ever needing the original datasets."]),
            ("How to Use It", "para", [
                "Open the website and follow the steps top to bottom: upload an iris, vet the message, hide it, encrypt it, send it, then receive it. Every step shows an explanation and its measurements, and the experiment log can be exported to CSV for the thesis."]),
        ]

    for title, kind, items in secs:
        p.heading(title)
        for it in items:
            if kind == "bullets":
                p.bullet(it)
            else:
                p.para(it)

    p.save()
    print("wrote", STATIC / f"thesis_guide_{d}.pdf")


if __name__ == "__main__":
    build(rtl=False)
    build(rtl=True)
