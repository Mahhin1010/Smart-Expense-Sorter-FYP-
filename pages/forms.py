"""
Forms for the Pages app.
Handles file uploads and validation for transaction imports.
"""
from django import forms
import os


class TransactionUploadForm(forms.Form):
    """
    Form for uploading CSV transaction files.
    Provides user-friendly error messages for unsupported file types.
    """
    file = forms.FileField(
        label="Select CSV File",
        help_text="Upload a .csv file with columns: Date, Description, Amount, Notes",
        widget=forms.FileInput(attrs={
            'accept': '.csv',
            'class': 'form-control',
            'id': 'csv-file-input'
        })
    )
    
    # Mapping of file extensions to helpful error messages with icon classes
    FILE_TYPE_ERRORS = {
        '.xlsx': ("Excel file detected! Please save as CSV from Excel: File → Save As → CSV (Comma delimited)", "fa-file-excel", "excel"),
        '.xls': ("Excel file detected! Please save as CSV from Excel: File → Save As → CSV (Comma delimited)", "fa-file-excel", "excel"),
        '.pdf': ("PDF files cannot be processed. Please export your bank statement as CSV.", "fa-file-pdf", "pdf"),
        '.json': ("JSON format is not supported. Please convert to CSV format.", "fa-file-code", "code"),
        '.xml': ("XML format is not supported. Please convert to CSV format.", "fa-file-code", "code"),
        '.txt': ("Text file detected. Please ensure it's saved as .csv with proper comma separation.", "fa-file-alt", "text"),
    }
    
    def clean_file(self):
        """
        Validate that the uploaded file is a CSV.
        Provides specific, helpful error messages for common file types.
        """
        uploaded_file = self.cleaned_data.get('file')
        
        if not uploaded_file:
            raise forms.ValidationError("Please select a file to upload.")
        
        # Get file extension
        file_name = uploaded_file.name
        _, file_extension = os.path.splitext(file_name.lower())
        
        # Check for valid CSV
        if file_extension == '.csv':
            return uploaded_file
        
        # Provide helpful error message for known file types
        if file_extension in self.FILE_TYPE_ERRORS:
            message, icon_class, file_type = self.FILE_TYPE_ERRORS[file_extension]
            raise forms.ValidationError(message, code=file_type, params={'icon': icon_class})
        
        # Generic error for unknown types
        raise forms.ValidationError(
            f"Unsupported file format '{file_extension}'. Please upload a .csv file.",
            code='unsupported'
        )
