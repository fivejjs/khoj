from datetime import datetime

import pytest

SKIP_TESTS = True
pytestmark = pytest.mark.skipif(
    SKIP_TESTS,
    reason="Disable in CI to avoid long test runs.",
)

import freezegun
from freezegun import freeze_time

from khoj.processor.conversation.offline.chat_model import (
    converse_offline,
    extract_questions_offline,
    filter_questions,
)
from khoj.processor.conversation.offline.utils import download_model
from khoj.processor.conversation.utils import message_to_log
from khoj.utils.constants import default_offline_chat_models


@pytest.fixture(scope="session")
def loaded_model():
    return download_model(default_offline_chat_models[0], max_tokens=5000)


freezegun.configure(extend_ignore_list=["transformers"])


# Test
# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
@freeze_time("1984-04-02", ignore=["transformers"])
def test_extract_question_with_date_filter_from_relative_day(loaded_model):
    # Act
    response = extract_questions_offline("Where did I go for dinner yesterday?", loaded_model=loaded_model)

    assert len(response) >= 1

    assert any(
        [
            "dt>='1984-04-01'" in response[0] and "dt<'1984-04-02'" in response[0],
            "dt>='1984-04-01'" in response[0] and "dt<='1984-04-01'" in response[0],
            'dt>="1984-04-01"' in response[0] and 'dt<"1984-04-02"' in response[0],
            'dt>="1984-04-01"' in response[0] and 'dt<="1984-04-01"' in response[0],
        ]
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.xfail(reason="Search actor still isn't very date aware nor capable of formatting")
@pytest.mark.chatquality
@freeze_time("1984-04-02", ignore=["transformers"])
def test_extract_question_with_date_filter_from_relative_month(loaded_model):
    # Act
    response = extract_questions_offline("Which countries did I visit last month?", loaded_model=loaded_model)

    # Assert
    assert len(response) >= 1
    # The user query should be the last question in the response
    assert response[-1] == ["Which countries did I visit last month?"]
    assert any(
        [
            "dt>='1984-03-01'" in response[0] and "dt<'1984-04-01'" in response[0],
            "dt>='1984-03-01'" in response[0] and "dt<='1984-03-31'" in response[0],
            'dt>="1984-03-01"' in response[0] and 'dt<"1984-04-01"' in response[0],
            'dt>="1984-03-01"' in response[0] and 'dt<="1984-03-31"' in response[0],
        ]
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.xfail(reason="Chat actor still isn't very date aware nor capable of formatting")
@pytest.mark.chatquality
@freeze_time("1984-04-02", ignore=["transformers"])
def test_extract_question_with_date_filter_from_relative_year():
    # Act
    response = extract_questions_offline("Which countries have I visited this year?")

    # Assert
    expected_responses = [
        ("dt>='1984-01-01'", ""),
        ("dt>='1984-01-01'", "dt<'1985-01-01'"),
        ("dt>='1984-01-01'", "dt<='1984-12-31'"),
    ]
    assert len(response) == 1
    assert any([start in response[0] and end in response[0] for start, end in expected_responses]), (
        "Expected date filter to limit to 1984 in response but got: " + response[0]
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_extract_multiple_explicit_questions_from_message(loaded_model):
    # Act
    responses = extract_questions_offline("What is the Sun? What is the Moon?", loaded_model=loaded_model)

    # Assert
    assert len(responses) >= 2
    assert ["the Sun" in response for response in responses]
    assert ["the Moon" in response for response in responses]


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_extract_multiple_implicit_questions_from_message(loaded_model):
    # Act
    response = extract_questions_offline("Is Carl taller than Ross?", loaded_model=loaded_model)

    # Assert
    expected_responses = ["height", "taller", "shorter", "heights", "who"]
    assert len(response) <= 3

    for question in response:
        assert any([expected_response in question.lower() for expected_response in expected_responses]), (
            "Expected chat actor to ask follow-up questions about Carl and Ross, but got: " + question
        )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_generate_search_query_using_question_from_chat_history(loaded_model):
    # Arrange
    message_list = [
        ("What is the name of Mr. Anderson's daughter?", "Miss Barbara", []),
    ]
    query = "Does he have any sons?"

    # Act
    response = extract_questions_offline(
        query,
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
        use_history=True,
    )

    any_expected_with_barbara = [
        "sibling",
        "brother",
    ]

    any_expected_with_anderson = [
        "son",
        "sons",
        "children",
        "family",
    ]

    # Assert
    assert len(response) >= 1
    # Ensure the remaining generated search queries use proper nouns and chat history context
    for question in response:
        if "Barbara" in question:
            assert any([expected_relation in question for expected_relation in any_expected_with_barbara]), (
                "Expected search queries using proper nouns and chat history for context, but got: " + question
            )
        elif "Anderson" in question:
            assert any([expected_response in question for expected_response in any_expected_with_anderson]), (
                "Expected search queries using proper nouns and chat history for context, but got: " + question
            )
        else:
            assert False, (
                "Expected search queries using proper nouns and chat history for context, but got: " + question
            )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_generate_search_query_using_answer_from_chat_history(loaded_model):
    # Arrange
    message_list = [
        ("What is the name of Mr. Anderson's daughter?", "Miss Barbara", []),
    ]

    # Act
    response = extract_questions_offline(
        "Is she a Doctor?",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
        use_history=True,
    )

    expected_responses = [
        "Barbara",
        "Anderson",
    ]

    # Assert
    assert len(response) >= 1
    assert any([expected_response in response[0] for expected_response in expected_responses]), (
        "Expected chat actor to mention person's by name, but got: " + response[0]
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.xfail(reason="Search actor unable to create date filter using chat history and notes as context")
@pytest.mark.chatquality
def test_generate_search_query_with_date_and_context_from_chat_history(loaded_model):
    # Arrange
    message_list = [
        ("When did I visit Masai Mara?", "You visited Masai Mara in April 2000", []),
    ]

    # Act
    response = extract_questions_offline(
        "What was the Pizza place we ate at over there?",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
    )

    # Assert
    expected_responses = [
        ("dt>='2000-04-01'", "dt<'2000-05-01'"),
        ("dt>='2000-04-01'", "dt<='2000-04-30'"),
        ('dt>="2000-04-01"', 'dt<"2000-05-01"'),
        ('dt>="2000-04-01"', 'dt<="2000-04-30"'),
    ]
    assert len(response) == 1
    assert "Masai Mara" in response[0]
    assert any([start in response[0] and end in response[0] for start, end in expected_responses]), (
        "Expected date filter to limit to April 2000 in response but got: " + response[0]
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_chat_with_no_chat_history_or_retrieved_content(loaded_model):
    # Act
    response_gen = converse_offline(
        references=[],  # Assume no context retrieved from notes for the user_query
        user_query="Hello, my name is Testatron. Who are you?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    expected_responses = ["Khoj", "khoj", "KHOJ"]
    assert len(response) > 0
    assert any([expected_response in response for expected_response in expected_responses]), (
        "Expected assistants name, [K|k]hoj, in response but got: " + response
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_answer_from_chat_history_and_previously_retrieved_content(loaded_model):
    "Chat actor needs to use context in previous notes and chat history to answer question"
    # Arrange
    message_list = [
        ("Hello, my name is Testatron. Who are you?", "Hi, I am Khoj, a personal assistant. How can I help?", []),
        (
            "When was I born?",
            "You were born on 1st April 1984.",
            ["Testatron was born on 1st April 1984 in Testville."],
        ),
    ]

    # Act
    response_gen = converse_offline(
        references=[],  # Assume no context retrieved from notes for the user_query
        user_query="Where was I born?",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    assert len(response) > 0
    # Infer who I am and use that to infer I was born in Testville using chat history and previously retrieved notes
    assert "Testville" in response


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_answer_from_chat_history_and_currently_retrieved_content(loaded_model):
    "Chat actor needs to use context across currently retrieved notes and chat history to answer question"
    # Arrange
    message_list = [
        ("Hello, my name is Testatron. Who are you?", "Hi, I am Khoj, a personal assistant. How can I help?", []),
        ("When was I born?", "You were born on 1st April 1984.", []),
    ]

    # Act
    response_gen = converse_offline(
        references=[
            {"compiled": "Testatron was born on 1st April 1984 in Testville."}
        ],  # Assume context retrieved from notes for the user_query
        user_query="Where was I born?",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    assert len(response) > 0
    assert "Testville" in response


# ----------------------------------------------------------------------------------------------------
@pytest.mark.xfail(reason="Chat actor lies when it doesn't know the answer")
@pytest.mark.chatquality
def test_refuse_answering_unanswerable_question(loaded_model):
    "Chat actor should not try make up answers to unanswerable questions."
    # Arrange
    message_list = [
        ("Hello, my name is Testatron. Who are you?", "Hi, I am Khoj, a personal assistant. How can I help?", []),
        ("When was I born?", "You were born on 1st April 1984.", []),
    ]

    # Act
    response_gen = converse_offline(
        references=[],  # Assume no context retrieved from notes for the user_query
        user_query="Where was I born?",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    expected_responses = [
        "don't know",
        "do not know",
        "no information",
        "do not have",
        "don't have",
        "cannot answer",
        "I'm sorry",
    ]
    assert len(response) > 0
    assert any([expected_response in response for expected_response in expected_responses]), (
        "Expected chat actor to say they don't know in response, but got: " + response
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_answer_requires_current_date_awareness(loaded_model):
    "Chat actor should be able to answer questions relative to current date using provided notes"
    # Arrange
    context = [
        {
            "compiled": f"""{datetime.now().strftime("%Y-%m-%d")} "Naco Taco" "Tacos for Dinner"
Expenses:Food:Dining  10.00 USD"""
        },
        {
            "compiled": f"""{datetime.now().strftime("%Y-%m-%d")} "Sagar Ratna" "Dosa for Lunch"
Expenses:Food:Dining  10.00 USD"""
        },
        {
            "compiled": f"""2020-04-01 "SuperMercado" "Bananas"
Expenses:Food:Groceries  10.00 USD"""
        },
        {
            "compiled": f"""2020-01-01 "Naco Taco" "Burittos for Dinner"
Expenses:Food:Dining  10.00 USD"""
        },
    ]

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="What did I have for Dinner today?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    expected_responses = ["tacos", "Tacos"]
    assert len(response) > 0
    assert any([expected_response in response for expected_response in expected_responses]), (
        "Expected [T|t]acos in response, but got: " + response
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_answer_requires_date_aware_aggregation_across_provided_notes(loaded_model):
    "Chat actor should be able to answer questions that require date aware aggregation across multiple notes"
    # Arrange
    context = [
        {
            "compiled": f"""# {datetime.now().strftime("%Y-%m-%d")} "Naco Taco" "Tacos for Dinner"
Expenses:Food:Dining  10.00 USD"""
        },
        {
            "compiled": f"""{datetime.now().strftime("%Y-%m-%d")} "Sagar Ratna" "Dosa for Lunch"
Expenses:Food:Dining  10.00 USD"""
        },
        {
            "compiled": f"""2020-04-01 "SuperMercado" "Bananas"
Expenses:Food:Groceries  10.00 USD"""
        },
        {
            "compiled": f"""2020-01-01 "Naco Taco" "Burittos for Dinner"
Expenses:Food:Dining  10.00 USD"""
        },
    ]

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="How much did I spend on dining this year?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    assert len(response) > 0
    assert "20" in response


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_answer_general_question_not_in_chat_history_or_retrieved_content(loaded_model):
    "Chat actor should be able to answer general questions not requiring looking at chat history or notes"
    # Arrange
    message_list = [
        ("Hello, my name is Testatron. Who are you?", "Hi, I am Khoj, a personal assistant. How can I help?", []),
        ("When was I born?", "You were born on 1st April 1984.", []),
        ("Where was I born?", "You were born Testville.", []),
    ]

    # Act
    response_gen = converse_offline(
        references=[],  # Assume no context retrieved from notes for the user_query
        user_query="Write a haiku about unit testing in 3 lines",
        conversation_log=populate_chat_history(message_list),
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    expected_responses = ["test", "testing"]
    assert len(response.splitlines()) >= 3  # haikus are 3 lines long, but Falcon tends to add a lot of new lines.
    assert any([expected_response in response.lower() for expected_response in expected_responses]), (
        "Expected [T|t]est in response, but got: " + response
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_ask_for_clarification_if_not_enough_context_in_question(loaded_model):
    "Chat actor should ask for clarification if question cannot be answered unambiguously with the provided context"
    # Arrange
    context = [
        {
            "compiled": f"""# Ramya
My sister, Ramya, is married to Kali Devi. They have 2 kids, Ravi and Rani."""
        },
        {
            "compiled": f"""# Fang
My sister, Fang Liu is married to Xi Li. They have 1 kid, Xiao Li."""
        },
        {
            "compiled": f"""# Aiyla
My sister, Aiyla is married to Tolga. They have 3 kids, Yildiz, Ali and Ahmet."""
        },
    ]

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="How many kids does my older sister have?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    expected_responses = ["which sister", "Which sister", "which of your sister", "Which of your sister", "Which one"]
    assert any([expected_response in response for expected_response in expected_responses]), (
        "Expected chat actor to ask for clarification in response, but got: " + response
    )


# ----------------------------------------------------------------------------------------------------
@pytest.mark.chatquality
def test_agent_prompt_should_be_used(loaded_model, offline_agent):
    "Chat actor should ask be tuned to think like an accountant based on the agent definition"
    # Arrange
    context = [
        {"compiled": f"""I went to the store and bought some bananas for 2.20"""},
        {"compiled": f"""I went to the store and bought some apples for 1.30"""},
        {"compiled": f"""I went to the store and bought some oranges for 6.00"""},
    ]

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="What did I buy?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert that the model without the agent prompt does not include the summary of purchases
    expected_responses = ["9.50", "9.5"]
    assert all([expected_response not in response for expected_response in expected_responses]), (
        "Expected chat actor to summarize values of purchases" + response
    )

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="What did I buy?",
        loaded_model=loaded_model,
        agent=offline_agent,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert that the model with the agent prompt does include the summary of purchases
    expected_responses = ["9.50", "9.5"]
    assert any([expected_response in response for expected_response in expected_responses]), (
        "Expected chat actor to summarize values of purchases" + response
    )


# ----------------------------------------------------------------------------------------------------
def test_chat_does_not_exceed_prompt_size(loaded_model):
    "Ensure chat context and response together do not exceed max prompt size for the model"
    # Arrange
    prompt_size_exceeded_error = "ERROR: The prompt size exceeds the context window size and cannot be processed"
    context = [{"compiled": " ".join([f"{number}" for number in range(2043)])}]

    # Act
    response_gen = converse_offline(
        references=context,  # Assume context retrieved from notes for the user_query
        user_query="What numbers come after these?",
        loaded_model=loaded_model,
    )
    response = "".join([response_chunk for response_chunk in response_gen])

    # Assert
    assert prompt_size_exceeded_error not in response, (
        "Expected chat response to be within prompt limits, but got exceeded error: " + response
    )


# ----------------------------------------------------------------------------------------------------
def test_filter_questions():
    test_questions = [
        "I don't know how to answer that",
        "I cannot answer anything about the nuclear secrets",
        "Who is on the basketball team?",
    ]
    filtered_questions = filter_questions(test_questions)
    assert len(filtered_questions) == 1
    assert filtered_questions[0] == "Who is on the basketball team?"


# Helpers
# ----------------------------------------------------------------------------------------------------
def populate_chat_history(message_list):
    # Generate conversation logs
    conversation_log = {"chat": []}
    for user_message, chat_response, context in message_list:
        message_to_log(
            user_message,
            chat_response,
            {"context": context, "intent": {"query": user_message, "inferred-queries": f'["{user_message}"]'}},
            conversation_log=conversation_log["chat"],
        )
    return conversation_log
