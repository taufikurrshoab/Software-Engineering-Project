from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("skill", "0004_learning_recommendations")]
    operations = [
        migrations.AddField(model_name="assessmentquestion", name="question_type", field=models.CharField(choices=[("mcq", "Multiple choice"), ("coding", "Coding task")], default="mcq", max_length=10)),
        migrations.AddField(model_name="assessmentquestion", name="coding_language", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="assessmentquestion", name="coding_submission", field=models.TextField(blank=True)),
        migrations.AddField(model_name="assessmentquestion", name="coding_score", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="assessmentquestion", name="coding_feedback", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="assessmentquestion", name="options", field=models.JSONField(blank=True, default=list)),
    ]
