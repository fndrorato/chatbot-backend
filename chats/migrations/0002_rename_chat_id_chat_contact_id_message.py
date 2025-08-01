# Generated by Django 5.2.4 on 2025-07-29 21:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chats', '0001_initial'),
        ('clients', '0002_alter_client_api_token'),
    ]

    operations = [
        migrations.RenameField(
            model_name='chat',
            old_name='chat_id',
            new_name='contact_id',
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contact_id', models.CharField(help_text='Unique identifier for the contact', max_length=255)),
                ('content_input', models.TextField(blank=True, help_text='Input content for the chat', null=True)),
                ('content_output', models.TextField(blank=True, help_text='Response content from the chat', null=True)),
                ('sender', models.CharField(help_text='Sender of the message', max_length=50)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='clients.client')),
            ],
            options={
                'verbose_name': 'Message',
                'verbose_name_plural': 'Messages',
                'ordering': ['timestamp'],
            },
        ),
    ]
