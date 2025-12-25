import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from pages.models import Transaction

# Create user
username = 'testuser_verify_csv'
password = 'testpassword123'
print(f"Creating/getting user {username}...")
if not User.objects.filter(username=username).exists():
    user = User.objects.create_user(username=username, password=password)
else:
    user = User.objects.get(username=username)

client = Client()
login_success = client.login(username=username, password=password)
print(f"Login successful: {login_success}")

# Create CSV content
csv_content = b"""Date,Description,Amount,Notes
2023-11-01,Test Transaction 1,123.45,First note
2023-11-02,Test Transaction 2,67.89,
InvalidDate,Bad Row,10.00,
2023-11-03,Test Transaction 3,10.00,Last note
"""

csv_file = SimpleUploadedFile("test_transactions.csv", csv_content, content_type="text/csv")

# Post to view
print("Uploading CSV to /upload/...")
response = client.post('/upload/', {'file': csv_file}, follow=True, HTTP_HOST='127.0.0.1')

print(f"Status Code: {response.status_code}")
# print(f"Response Content Preview: {response.content.decode('utf-8', errors='ignore')[:1000]}")


if response.context and 'form' in response.context:
    print(f"Form Errors: {response.context['form'].errors}")

# Check messages
print("Messages:")
messages = list(response.context['messages']) if response.context and 'messages' in response.context else []
for m in messages:
    print(f" - [{m.level_tag.upper()}] {m.message}")

# Check transactions
transactions = Transaction.objects.filter(user=user)
count = transactions.count()
print(f"\nTransactions in DB for user (Expected 3): {count}")
for t in transactions:
    print(f" - {t.date}: {t.description} | ${t.amount} | {t.notes}")

if count == 3:
    print("\nSUCCESS: Verification Passed! 3 valid transactions imported.")
else:
    print(f"\nFAILURE: Expected 3 transactions, found {count}.")

# Cleanup
# Transaction.objects.filter(user=user).delete()
# user.delete()
