from django.db import migrations, models

class Migration(migrations.Migration):

    # Make this a no-op that depends on the newer migration to avoid conflicts
    dependencies = [
        ('base', '0018_add_loose_pieces_to_stockbatch'),
    ]

    operations = []
