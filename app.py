import streamlit as st

from research_assistant import (
    search_all_sources,
    extract_pdf_text_chunked,
    answer_with_rag,
    generate_paper_report,
    answer_question_about_selected_paper,
    chatbot_answer,
    generate_advanced_code,
    generate_pdf_summary_report,
    compare_two_papers_rag,
)

# ============================================================
# STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="AI Research Assistant",
    layout="wide",
    page_icon="🤖",
)

st.title("🤖 AI Research Assistant")
st.caption(
    "Multi-source paper search · PDF RAG Q&A · Chatbot · Code Generator · Paper Reports"
)
st.markdown("---")

# ============================================================
# SESSION STATE INIT
# ============================================================
if "papers" not in st.session_state:
    st.session_state["papers"] = []

if "paper_report" not in st.session_state:
    st.session_state["paper_report"] = None

if "paper_report_key" not in st.session_state:
    st.session_state["paper_report_key"] = None

if "paper_chat_history" not in st.session_state:
    # {paper_key: [ {role, content}, ... ]}
    st.session_state["paper_chat_history"] = {}

if "pdf_data" not in st.session_state:
    st.session_state["pdf_data"] = None

if "pdf_report" not in st.session_state:
    st.session_state["pdf_report"] = None

if "chatbot_history" not in st.session_state:
    st.session_state["chatbot_history"] = []

if "compare_result" not in st.session_state:
    st.session_state["compare_result"] = None


# ============================================================
# TABS
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🔍 Search Papers",
        "📄 PDF Upload + RAG Q&A",
        "💬 Chatbot",
        "💻 Code Generator",
        "📊 Compare Papers",
    ]
)

# ============================================================
# TAB 1 — SEARCH PAPERS + PAPER REPORT + Q&A
# ============================================================
with tab1:
    st.header("🔍 Search Papers")

    topic = st.text_input(
        "Enter a search topic:",
        placeholder="e.g., image segmentation, transformer models, medical imaging",
        key="search_topic",
    )

    if st.button("Search", key="search_btn"):
        if not topic.strip():
            st.warning("Please enter a topic.")
        else:
            with st.spinner("Searching Semantic Scholar + arXiv..."):
                papers = search_all_sources(topic)
            st.session_state["papers"] = papers
            st.session_state["paper_report"] = None
            st.session_state["paper_report_key"] = None
            st.session_state["paper_chat_history"] = {}
            if not papers:
                st.error("No papers found. Try another query.")
            else:
                st.success(f"Found {len(papers)} related papers.")

    papers = st.session_state["papers"]

    if papers:
        titles = [f"{i+1}. {p['title']}" for i, p in enumerate(papers)]

        selected_index = st.selectbox(
            "Select a paper:",
            range(len(papers)),
            format_func=lambda i: titles[i],
            key="selected_paper_idx",
        )
        paper = papers[selected_index]

        paper_key = f"{paper.get('title','')}|{paper.get('source','')}"
        authors_str = ", ".join(paper.get("authors", [])) or "Unknown"

        st.subheader("Paper Details")
        st.markdown(f"**Title:** {paper.get('title','')}")
        st.markdown(f"**Authors:** {authors_str}")
        st.markdown(f"**Year:** {paper.get('year','Unknown')}")
        st.markdown(f"**Venue:** {paper.get('venue','Unknown')}")
        st.markdown(f"**Citations:** {paper.get('citations',0)}")
        st.markdown(f"**Source:** {paper.get('source','')}")
        if paper.get("url"):
            st.markdown(f"**URL:** [{paper['url']}]({paper['url']})")

        st.markdown("")

        col_rep, col_q = st.columns([1, 1])

        # ----- Generate Report -----
        with col_rep:
            if st.button("📝 Generate Paper Report", key="gen_paper_report_btn"):
                with st.spinner("Generating report from abstract..."):
                    report = generate_paper_report(paper)
                st.session_state["paper_report"] = report
                st.session_state["paper_report_key"] = paper_key

        # ----- Paper Report Display (Persistent) -----
        if (
            st.session_state["paper_report"]
            and st.session_state["paper_report_key"] == paper_key
        ):
            st.markdown("### 📄 Paper Report")
            st.markdown(st.session_state["paper_report"])

            st.download_button(
                "⬇️ Download Paper Report (Markdown)",
                st.session_state["paper_report"],
                file_name="paper_report.md",
                mime="text/markdown",
                key="download_paper_report_btn",
            )

        st.markdown("---")

        # ----- Paper Q&A with chat history -----
        st.subheader("❓ Ask a Question About This Paper")

        question = st.text_input(
            "Your question:",
            placeholder="e.g., What dataset is used? What is the main contribution?",
            key="paper_question_input",
        )

        if st.button("Ask About Paper", key="ask_paper_question_btn"):
            if not question.strip():
                st.warning("Please enter a question.")
            else:
                history_dict = st.session_state["paper_chat_history"]
                history = history_dict.get(paper_key, []).copy()

                with st.spinner("Answering from the abstract..."):
                    answer = answer_question_about_selected_paper(
                        paper, question, history=history
                    )

                # update history (user + assistant)
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})
                history_dict[paper_key] = history
                st.session_state["paper_chat_history"] = history_dict

        # Show chat history for this paper
        history = st.session_state["paper_chat_history"].get(paper_key, [])
        if history:
            st.markdown("#### Chat History for This Paper")
            for msg in history:
                if msg["role"] == "user":
                    st.markdown(f"**🧑‍💻 You:** {msg['content']}")
                else:
                    st.markdown(f"**🤖 Assistant:** {msg['content']}")


# ============================================================
# TAB 2 — PDF UPLOAD + RAG Q&A + SUMMARY
# ============================================================
with tab2:
    st.header("📄 PDF Upload + RAG-Based Question Answering")

    pdf = st.file_uploader(
        "Upload a PDF file", type=["pdf"], key="pdf_uploader_main"
    )

    if pdf is not None and st.button("Process PDF", key="process_pdf_btn"):
        with st.spinner("Extracting text and creating chunks..."):
            pdf_data = extract_pdf_text_chunked(pdf)
        st.session_state["pdf_data"] = pdf_data
        st.session_state["pdf_report"] = None
        st.success("PDF loaded and processed successfully!")

    pdf_data = st.session_state["pdf_data"]

    if pdf_data:
        st.success("PDF is ready for Q&A and summary.")

        # ----- Q&A -----
        st.subheader("❓ Ask a question about the PDF")

        pdf_question = st.text_input(
            "Question:",
            placeholder="e.g., What is NFA? What is the main conclusion?",
            key="pdf_question_input",
        )

        if st.button("Ask PDF", key="ask_pdf_btn"):
            if not pdf_question.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Answering using RAG..."):
                    answer = answer_with_rag(pdf_data["chunks"], pdf_question)
                st.markdown("### Answer")
                st.markdown(answer)

        st.markdown("---")

        # ----- Summary Report -----
        st.subheader("📘 PDF Summary Report")

        if st.button("Generate PDF Summary Report", key="gen_pdf_report_btn"):
            with st.spinner("Summarizing PDF content..."):
                pdf_report = generate_pdf_summary_report(pdf_data["full_text"])
            st.session_state["pdf_report"] = pdf_report

        if st.session_state["pdf_report"]:
            st.markdown("### Summary")
            st.markdown(st.session_state["pdf_report"])

            st.download_button(
                "⬇️ Download PDF Summary (Markdown)",
                st.session_state["pdf_report"],
                file_name="pdf_summary.md",
                mime="text/markdown",
                key="download_pdf_report_btn",
            )


# ============================================================
# TAB 3 — GENERAL CHATBOT
# ============================================================
with tab3:
    st.header("💬 Research Chatbot")

    user_message = st.text_area(
        "Ask anything (research questions, explanations, brainstorming, etc.):",
        key="chatbot_message_input",
        placeholder="e.g., Explain the difference between CNNs and Transformers.",
        height=120,
    )

    if st.button("Send", key="chatbot_send_btn"):
        if not user_message.strip():
            st.warning("Please enter a message.")
        else:
            history = st.session_state["chatbot_history"].copy()

            with st.spinner("Thinking..."):
                reply = chatbot_answer(user_message, history=history)

            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            st.session_state["chatbot_history"] = history

    history = st.session_state["chatbot_history"]
    if history:
        st.markdown("### Chat History")
        for msg in history:
            if msg["role"] == "user":
                st.markdown(f"**🧑‍💻 You:** {msg['content']}")
            else:
                st.markdown(f"**🤖 Assistant:** {msg['content']}")


# ============================================================
# TAB 4 — CODE GENERATOR
# ============================================================
with tab4:
    st.header("💻 Code Generator")

    task = st.text_area(
        "Describe the coding task:",
        placeholder=(
            "Examples:\n"
            "- Implement a Python class for a simple queue.\n"
            "- PyTorch CNN model for CIFAR-10.\n"
            "- FastAPI endpoint that returns JSON.\n"
        ),
        key="code_task_input",
        height=160,
    )

    language = st.selectbox(
        "Language:", ["python", "cpp", "java", "javascript", "typescript"], key="code_lang_select"
    )

    if st.button("Generate Code", key="gen_code_btn"):
        if not task.strip():
            st.warning("Please describe a coding task.")
        else:
            with st.spinner("Generating code..."):
                code = generate_advanced_code(task, language=language)
            st.markdown("### Generated Code")
            st.code(code, language=language)

            st.download_button(
                "⬇️ Download Code",
                code,
                file_name=f"generated_code.{language}",
                mime="text/plain",
                key="download_code_btn",
            )


# ============================================================
# TAB 5 — COMPARE PAPERS (ABSTRACT-BASED)
# ============================================================
with tab5:
    st.header("📊 Compare Papers (Abstract-Based)")

    papers = st.session_state["papers"]
    if not papers:
        st.info("Please search for papers in the 'Search Papers' tab first.")
    else:
        titles = [f"{i+1}. {p['title']}" for i, p in enumerate(papers)]

        col1, col2 = st.columns(2)
        with col1:
            idx1 = st.selectbox(
                "Select first paper",
                range(len(papers)),
                format_func=lambda i: titles[i],
                key="cmp_paper1",
            )
        with col2:
            idx2 = st.selectbox(
                "Select second paper",
                range(len(papers)),
                format_func=lambda i: titles[i],
                key="cmp_paper2",
            )

        aspect = st.selectbox(
            "Aspect to compare:",
            ["methodology", "results", "applications", "overall quality"],
            key="cmp_aspect",
        )

        if st.button("Compare", key="cmp_btn"):
            if idx1 == idx2:
                st.warning("Please select two different papers.")
            else:
                text1 = papers[idx1].get("abstract", "")
                text2 = papers[idx2].get("abstract", "")
                if not text1 or not text2:
                    st.error("One of the selected papers has no abstract.")
                else:
                    with st.spinner("Comparing papers..."):
                        cmp_result = compare_two_papers_rag(text1, text2, aspect)
                    st.session_state["compare_result"] = cmp_result

        if st.session_state["compare_result"]:
            st.markdown("### Comparison Result")
            st.markdown(st.session_state["compare_result"])
