from django import forms
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError

ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

class GenerateForm(forms.Form):
    document = forms.FileField(
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "docx"])]
    )

    def clean_document(self):
        f = self.cleaned_data["document"]
        content_type = getattr(f, "content_type", "") or ""
        if content_type not in ALLOWED_MIME:
            raise ValidationError("Unsupported file type. Allowed: .pdf, .docx")
        return f
