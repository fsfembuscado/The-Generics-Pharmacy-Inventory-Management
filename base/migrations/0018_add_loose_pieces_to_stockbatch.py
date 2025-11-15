from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0017_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockbatch',
            name='loose_pieces',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
