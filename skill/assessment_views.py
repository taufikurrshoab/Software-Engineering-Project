import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .adaptive import next_difficulty, weighted_percentage
from .assessment_services import generate_question, generate_coding_task, grade_coding_submission
from .models import Assessment, AssessmentQuestion, Skill


QUESTION_COUNT = 5


def _skill_assessment_context(skill):
    """Build the full parent-to-child skill path and detect its language.

    Child skills such as 'Loops' inherit the language from a parent such as
    'C++' or 'Python', preventing the model from guessing from the child name.
    """
    nodes = []
    node = skill
    seen = set()
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        nodes.append(node.name.strip())
        node = node.parent
    nodes.reverse()
    path = " > ".join(nodes)

    aliases = [
        ("C++", ("c++", "cpp", "c plus plus")),
        ("C#", ("c#", "c sharp", "csharp")),
        ("JavaScript", ("javascript", "js")),
        ("TypeScript", ("typescript", "ts")),
        ("Python", ("python", "py")),
        ("Java", ("java",)),
        ("C", ("c",)),
        ("Go", ("golang", "go")),
        ("Rust", ("rust",)),
        ("PHP", ("php",)),
        ("Ruby", ("ruby",)),
        ("Kotlin", ("kotlin",)),
        ("Swift", ("swift",)),
        ("SQL", ("sql",)),
    ]
    import re
    language = None
    for canonical, terms in aliases:
        for term in terms:
            pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
            if re.search(pattern, path, flags=re.IGNORECASE):
                language = canonical
                break
        if language:
            break
    return path, language


def _ensure_question(assessment):
    """Return the current unanswered question, generating it only when needed."""
    question_number = assessment.answered_questions + 1
    existing = assessment.questions.filter(question_number=question_number).first()
    if existing:
        return existing

    previous_questions = list(
        assessment.questions.values_list("question_text", flat=True)
    )
    skill_context, programming_language = _skill_assessment_context(assessment.skill)
    is_coding = question_number == assessment.total_questions and assessment.total_questions >= 5
    if is_coding:
        generated = generate_coding_task(
            skill_context, assessment.next_difficulty,
            programming_language=programming_language,
        )
        values = {
            "question_type": "coding", "topic": generated["topic"],
            "question_text": generated["prompt"], "options": [],
            "correct_index": 0, "explanation": "Your submitted code will be reviewed by the AI grader.",
            "coding_language": generated["language"],
        }
    else:
        generated = generate_question(
            skill_context, assessment.next_difficulty,
            previous_questions=previous_questions,
            programming_language=programming_language,
        )
        values = {
            "question_type": "mcq", "topic": generated["topic"],
            "question_text": generated["question"], "options": generated["options"],
            "correct_index": generated["correct_index"], "explanation": generated["explanation"],
        }
    try:
        return AssessmentQuestion.objects.create(
            assessment=assessment, question_number=question_number,
            difficulty=assessment.next_difficulty, **values,
        )
    except IntegrityError:
        return assessment.questions.get(question_number=question_number)


@login_required
@require_POST
def assessment_start(request, skill_id):
    skill = get_object_or_404(Skill, pk=skill_id, user=request.user)

    # If an attempt is already in progress, continue it instead of creating
    # multiple active attempts for the same skill.
    active = Assessment.objects.filter(
        user=request.user, skill=skill, status=Assessment.Status.ACTIVE
    ).first()
    if active:
        return redirect("skill:assessment_take", assessment_id=active.pk)

    assessment = Assessment.objects.create(
        user=request.user,
        skill=skill,
        total_questions=QUESTION_COUNT,
        next_difficulty="beginner",
    )
    messages.info(request, f"Your {skill.name} assessment is ready. Let's begin.")
    return redirect("skill:assessment_take", assessment_id=assessment.pk)


@login_required
def assessment_take(request, assessment_id):
    assessment = get_object_or_404(
        Assessment, pk=assessment_id, user=request.user
    )
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("skill:assessment_result", assessment_id=assessment.pk)

    question = None
    generation_error = None
    try:
        question = _ensure_question(assessment)
    except Exception as exc:
        generation_error = str(exc)
        messages.error(request, f"Could not generate a question: {generation_error}")

    return render(request, "skill/assessment_take.html", {
        "assessment": assessment,
        "question": question,
        "generation_error": generation_error,
    })


@login_required
@require_POST
def assessment_answer(request, assessment_id, question_id):
    assessment = get_object_or_404(
        Assessment,
        pk=assessment_id,
        user=request.user,
        status=Assessment.Status.ACTIVE,
    )
    question = get_object_or_404(
        AssessmentQuestion,
        pk=question_id,
        assessment=assessment,
        question_number=assessment.answered_questions + 1,
    )

    if question.question_type == "coding":
        submission = request.POST.get("code_submission", "").strip()
        if not submission:
            messages.error(request, "Please enter your code before submitting.")
            return redirect("skill:assessment_take", assessment_id=assessment.pk)
        if len(submission) > 20000:
            messages.error(request, "Your code is too long. Keep it under 20,000 characters.")
            return redirect("skill:assessment_take", assessment_id=assessment.pk)
        try:
            skill_context, _ = _skill_assessment_context(assessment.skill)
            coding_score, feedback = grade_coding_submission(
                skill_context, question.coding_language,
                question.question_text, submission,
            )
        except Exception as exc:
            messages.error(request, f"Your code was not submitted because AI marking failed: {exc}")
            return redirect("skill:assessment_take", assessment_id=assessment.pk)
        with transaction.atomic():
            question.coding_submission = submission
            question.coding_score = coding_score
            question.coding_feedback = feedback
            question.is_correct = coding_score >= 60
            question.selected_index = 0
            question.save(update_fields=["coding_submission", "coding_score", "coding_feedback", "is_correct", "selected_index"])
            assessment.answered_questions += 1
            finished = assessment.answered_questions >= assessment.total_questions
            if finished:
                assessment.status = Assessment.Status.COMPLETED
                assessment.completed_at = timezone.now()
                assessment.score = weighted_percentage(assessment.questions.filter(selected_index__isnull=False))
            assessment.save()
            if finished:
                skill = assessment.skill
                was_completed = skill.is_completed
                skill.progress = int(round(float(assessment.score)))
                skill.save()
                if skill.is_completed and not was_completed:
                    request.session["skill_just_completed"] = skill.pk
        if finished:
            messages.success(request, f"Assessment complete! Coding task score: {coding_score}/100.")
            return redirect("skill:assessment_result", assessment_id=assessment.pk)
        return redirect("skill:assessment_take", assessment_id=assessment.pk)

    raw_choice = request.POST.get("choice", "")
    try:
        selected_index = int(raw_choice)
    except (TypeError, ValueError):
        messages.error(request, "Please select one answer before continuing.")
        return redirect("skill:assessment_take", assessment_id=assessment.pk)

    if selected_index not in range(4):
        return HttpResponseBadRequest("Invalid answer option.")

    if question.selected_index is not None:
        return redirect("skill:assessment_take", assessment_id=assessment.pk)

    with transaction.atomic():
        question.selected_index = selected_index
        question.is_correct = selected_index == question.correct_index
        question.save(update_fields=["selected_index", "is_correct"])

        assessment.answered_questions += 1
        assessment.next_difficulty = next_difficulty(
            question.difficulty, question.is_correct
        )

        finished = assessment.answered_questions >= assessment.total_questions
        if finished:
            assessment.status = Assessment.Status.COMPLETED
            assessment.completed_at = timezone.now()
            assessment.score = weighted_percentage(
                assessment.questions.filter(selected_index__isnull=False)
            )
        assessment.save()

        if finished:
            skill = assessment.skill
            was_completed = skill.is_completed
            skill.progress = int(round(float(assessment.score)))
            skill.save()
            if skill.is_completed and not was_completed:
                request.session["skill_just_completed"] = skill.pk

    if finished:
        messages.success(
            request,
            f"Assessment complete! Your {assessment.skill.name} proficiency is {assessment.score:.0f}%.",
        )
        return redirect("skill:assessment_result", assessment_id=assessment.pk)

    # Generate the next question now; if the API is temporarily unavailable,
    # the next page load retries because no question has been stored yet.
    try:
        _ensure_question(assessment)
    except Exception as exc:
        messages.error(request, f"Your answer was saved, but the next question could not be generated: {exc}")

    return redirect("skill:assessment_take", assessment_id=assessment.pk)


@login_required
def assessment_result(request, assessment_id):
    assessment = get_object_or_404(
        Assessment,
        pk=assessment_id,
        user=request.user,
        status=Assessment.Status.COMPLETED,
    )
    questions = assessment.questions.all()
    correct_count = questions.filter(question_type="mcq", is_correct=True).count()
    coding_question = questions.filter(question_type="coding").first()
    return render(request, "skill/assessment_result.html", {
        "assessment": assessment,
        "questions": questions,
        "correct_count": correct_count,
        "coding_question": coding_question,
    })


@login_required
def assessment_history(request, skill_id):
    skill = get_object_or_404(Skill, pk=skill_id, user=request.user)
    attempts = Assessment.objects.filter(
        user=request.user, skill=skill, status=Assessment.Status.COMPLETED
    )
    return render(request, "skill/assessment_history.html", {
        "skill": skill,
        "attempts": attempts,
    })
