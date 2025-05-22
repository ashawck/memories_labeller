import streamlit as st
import json
import html
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# --- Configuration ---
LABEL_CLASSIFICATIONS = [
    "Correct 👍",
    "Incorrect 👎",
    "I'm not sure 🤔",
]
DEFAULT_OUTPUT_FILENAME = "alerts_labeled_tp_fp_tn_fn.jsonl"
READABLE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
BRAND_COLOR = "#df0074"  # Visory signature pink color

# --- Custom styling with the brand color ---
def apply_custom_styling():
    # Apply brand colors to various elements
    st.markdown(f"""
    <style>
        /* Brand color for headers */
        h1, h2, h3, h4, h5, h6 {{
            color: {BRAND_COLOR} !important;
        }}
        
        /* Brand color for links */
        a {{
            color: {BRAND_COLOR} !important;
        }}
        
        /* Style the progress bar with brand color */
        .stProgress > div > div > div > div {{
            background-color: {BRAND_COLOR} !important;
        }}
        
        /* Style buttons with brand color */
        .stButton>button {{
            border-color: {BRAND_COLOR} !important;
            color: {BRAND_COLOR} !important;
        }}
        
        .stButton>button:hover {{
            background-color: {BRAND_COLOR} !important;
            color: white !important;
        }}
        
        /* Style the radio buttons and checkboxes */
        .stRadio label, .stCheckbox label {{
            color: {BRAND_COLOR} !important;
        }}
        
        /* Add a subtle brand-colored border to expanders */
        .streamlit-expanderHeader {{
            border-left: 2px solid {BRAND_COLOR} !important;
            padding-left: 5px !important;
        }}
        
        /* Add a subtle accent to download button */
        .stDownloadButton>button {{
            background-color: {BRAND_COLOR} !important;
            color: white !important;
        }}
        
        /* Highlight sidebar header with brand color */
        .sidebar .sidebar-content h2 {{
            color: {BRAND_COLOR} !important;
        }}
    </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---

@st.cache_data
def load_data_and_labels(uploaded_file):
    """
    Loads data from the uploaded JSONL file.
    If the file contains existing labels, it extracts them.
    Returns both the list of data records and a dictionary of labels.
    """
    data = []
    loaded_labels = {}  # Dictionary to store labels found in the file
    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            lines = uploaded_file.readlines()
            # Hide technical messages from users
            for i, line_bytes in enumerate(lines):
                try:
                    line_str = line_bytes.decode('utf-8').strip()
                    if line_str:
                        record = json.loads(line_str)
                        
                        # Process the record to match our expected structure
                        processed_record = transform_record(record)
                        if processed_record:
                            data.append(processed_record)

                            # Check for and extract existing labels
                            record_id = processed_record.get("observation_id")
                            if record_id and "human_label_classification" in processed_record:
                                loaded_labels[record_id] = {
                                    "human_label_timestamp": processed_record.get("human_label_timestamp", datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')),
                                    "human_label_classification": processed_record.get("human_label_classification", LABEL_CLASSIFICATIONS[-1]),
                                    "human_label_critique": processed_record.get("human_label_critique", ""),
                                    "human_label_correct_memory_optional": processed_record.get("human_label_correct_memory_optional", ""),
                                }
                except json.JSONDecodeError:
                    # Silently skip invalid JSON without showing warnings
                    pass
                except UnicodeDecodeError:
                    # Silently skip decoding errors without showing warnings
                    pass
                except Exception as e:
                    # Silently handle errors without showing warnings
                    pass

            # No summary messages after processing

            return data, loaded_labels  # Return both data and labels

        except Exception as e:
            # Only show error for critical failures
            st.error("There was a problem loading the file. Please make sure it's a valid JSONL file.")
            return [], {}  # Return empty on major failure
    return [], {}  # Return empty if no file

def transform_record(record):
    """Transform the record from your JSON format to the expected format for the labeling tool."""
    try:
        # Extract basic info - use the appropriate fields from your data
        observation_id = record.get("id") or record.get("traceId") 
        if not observation_id:
            return None
        
        # Extract LLM output, which should contain any memory tags
        llm_output = ""
        if "output" in record:
            llm_output = record["output"]
        
        # Extract system prompts
        system_prompt = ""
        if "input" in record and "messages" in record["input"]:
            for msg in record["input"]["messages"]:
                if msg.get("role") == "system":
                    system_prompt += msg.get("content", "") + "\n\n"
        
        # Try to extract chat history
        chat_history = []
        try:
            # Look for chat history in different possible locations
            if "input" in record and "messages" in record["input"]:
                for msg in record["input"]["messages"]:
                    content = msg.get("content", "")
                    if "Chat history" in content and "[" in content and "]" in content:
                        # Try to extract the JSON array from the content
                        start_idx = content.find("[")
                        end_idx = content.rfind("]") + 1
                        if start_idx > 0 and end_idx > start_idx:
                            try:
                                history_str = content[start_idx:end_idx]
                                extracted_history = json.loads(history_str)
                                if isinstance(extracted_history, list):
                                    chat_history = extracted_history
                            except:
                                pass
        except Exception as e:
            st.warning(f"Error extracting chat history: {e}")
        
        # Extract existing memories
        existing_memories = []
        try:
            if "input" in record and "messages" in record["input"]:
                for msg in record["input"]["messages"]:
                    content = msg.get("content", "")
                    if "Current memories" in content and "```" in content:
                        # Try to extract the JSON array from between the code blocks
                        start_idx = content.find("```") + 3
                        content = content[start_idx:]
                        end_idx = content.find("```")
                        if end_idx > 0:
                            try:
                                memories_str = content[:end_idx].strip()
                                extracted_memories = json.loads(memories_str)
                                if isinstance(extracted_memories, list):
                                    existing_memories = extracted_memories
                            except:
                                pass
        except Exception as e:
            st.warning(f"Error extracting existing memories: {e}")
        
        # Extract chat metadata
        chat_metadata = {}
        try:
            if "input" in record and "messages" in record["input"]:
                for msg in record["input"]["messages"]:
                    content = msg.get("content", "")
                    if "Chat metadata" in content and "```" in content:
                        # Try to extract the JSON object from between the code blocks
                        start_idx = content.find("```") + 3
                        content = content[start_idx:]
                        end_idx = content.find("```")
                        if end_idx > 0:
                            try:
                                metadata_str = content[:end_idx].strip()
                                extracted_metadata = json.loads(metadata_str)
                                if isinstance(extracted_metadata, dict):
                                    chat_metadata = extracted_metadata
                            except:
                                pass
        except Exception as e:
            st.warning(f"Error extracting chat metadata: {e}")
        
        # Determine alert type based on the presence of <MEMORY> tags in the output
        alert_type = "memory" if "<MEMORY" in llm_output else "no_memory"
            
        # Construct the transformed record with all needed fields
        transformed_record = {
            "observation_id": observation_id,
            "llm_output": llm_output,
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "existing_memories": existing_memories,
            "chat_metadata": chat_metadata,
            "alert_type": alert_type,
            # Add any other fields you might need
        }
        
        return transformed_record
    
    except Exception as e:
        st.warning(f"Error transforming record: {e}")
        return None

# --- Function to Apply Filter ---
def apply_filter():
    """
    Previously used to filter data based on MEMORY tags.
    Now just saves the current state and ensures all data is shown.
    Kept for compatibility.
    """
    # Save current label state before potentially changing index/data
    # Check if data exists and index is valid before saving
    if st.session_state.data and 0 <= st.session_state.index < len(st.session_state.data):
        current_record_id = st.session_state.data[st.session_state.index].get("observation_id")
        if current_record_id:
            save_labels_to_state(st.session_state.index, current_record_id)

    # Always show all data (filter removed)
    st.session_state.data = st.session_state.all_data
    
    # Reset index whenever filter changes
    st.session_state.index = 0

# --- Navigation Callbacks ---
def go_previous():
    """Saves current state and decrements the index."""
    # Check if data exists and index is valid before saving
    if st.session_state.data and 0 <= st.session_state.index < len(st.session_state.data):
        current_record_id = st.session_state.data[st.session_state.index].get("observation_id")
        if current_record_id:
            save_labels_to_state(st.session_state.index, current_record_id)
    if st.session_state.index > 0:
        st.session_state.index -= 1

def go_next():
    """Saves current state and increments the index."""
    # Check if data exists and index is valid before saving
    if st.session_state.data and 0 <= st.session_state.index < len(st.session_state.data):
        current_record_id = st.session_state.data[st.session_state.index].get("observation_id")
        if current_record_id:
            save_labels_to_state(st.session_state.index, current_record_id)
    # Check against the length of the *currently displayed* data list
    if st.session_state.index < len(st.session_state.data) - 1:
        st.session_state.index += 1

def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    if not isinstance(text, str): return text
    parts = text.split()
    return ' '.join(parts) if parts else ''

def format_chat_history(chat_history):
    display_lines = []
    if not isinstance(chat_history, list): return ["Invalid chat history format."]
    for msg in chat_history:
        name = msg.get("name", "Unknown")
        role = msg.get("role", "Unknown")
        timestamp_str = msg.get("createdAt", "")
        message = msg.get("message", "*No message content*")
        actor_id = msg.get("actorId", "")
        readable_timestamp = "Invalid Timestamp"
        if timestamp_str:
            try:
                dt_object = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                readable_timestamp = dt_object.strftime(READABLE_TIMESTAMP_FORMAT)
            except ValueError: readable_timestamp = timestamp_str
        # Use brand color for the name to make it stand out
        display_lines.append(f"<span style='color:{BRAND_COLOR};font-weight:bold;'>{name} ({role})</span> [{readable_timestamp}] *(Actor: {actor_id})*\n> {message}\n---")
    return display_lines

def save_labels_to_state(current_index, record_id):
    if 'labels' not in st.session_state: st.session_state.labels = {}
    classification_key = f"label_classification_{record_id}"
    classification_value = st.session_state.get(classification_key, LABEL_CLASSIFICATIONS[-1])
    current_labels = {
        "human_label_timestamp": datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
        "human_label_classification": classification_value,
        "human_label_critique": st.session_state.get(f"critique_{record_id}", ""),
        "human_label_correct_memory_optional": st.session_state.get(f"correct_mem_{record_id}", ""),
    }
    st.session_state.labels[record_id] = current_labels

def generate_labeled_data_jsonl():
    labeled_data = []
    # Iterate over the original full dataset (all_data)
    if st.session_state.get('all_data') and st.session_state.get('labels'):
        if not st.session_state.all_data: return ""
        # Use all_data to ensure all records are considered for saving
        for record in st.session_state.all_data:
            record_id = record.get("observation_id")
            if record_id is None: continue
            merged_record = record.copy() # Start with original record data
            # Check if labels exist for this record_id in the state and update
            if record_id in st.session_state.labels:
                merged_record.update(st.session_state.labels[record_id])
                # Only append records that have been labeled during the session
                try:
                    labeled_data.append(json.dumps(merged_record, ensure_ascii=False))
                except TypeError as e:
                    st.error(f"Error serializing record {record_id}: {e}. Skipping.")

    return "\n".join(labeled_data)


# --- Streamlit App Layout ---

st.set_page_config(layout="wide", page_title="Visory AI Memory Labelling Tool")

# Apply custom styling with brand colors
apply_custom_styling()

# Add branded logo - this always shows
st.markdown(f"""
    <h1 style='color:{BRAND_COLOR};'>Visory AI Memory Labelling Tool</h1>
    <h2 style='color:{BRAND_COLOR};text-align:center;'>🌟 Welcome to Visory's Delphi AI Memory Labelling Tool! 🌟</h2>
""", unsafe_allow_html=True)

# Determine if instructions should be expanded by default
# (expanded when no file is loaded, collapsed when a file is loaded)
show_instructions = len(st.session_state.get('data', [])) == 0

# Put instructions in an expander
with st.expander("How to use this tool", expanded=show_instructions):
    st.markdown(f"""
        <p>Hi there, valued expert! We're excited you're here to help Delphi, our clever AI assistant, get smarter at recognising useful memories.</p>
        
        <p style='color:{BRAND_COLOR};font-weight:bold;margin-top:20px;'>🚀 How to Jump In:</p>
        <p>1. <b>📁 Upload Your Document</b> Use the sidebar on the left to upload your JSONL file. Each line should be a neatly formatted JSON object representing an AI conversation.</p>
        
        <p>2. <b>🔍 Review Delphi's Memory</b> You'll see one memory at a time, including Delphi's determination about whether it's useful.</p>
        
        <p>3. <b>✅ Label Delphi's Decision</b> Help Delphi learn by telling it how it did:</p>
        <p style='margin-left:20px;'><b>Correct 👍</b>: Delphi nailed it!</p>
        <p style='margin-left:20px;'><b>Incorrect 👎</b>: Delphi missed the mark.</p>
        <p style='margin-left:20px;'><b>I'm not sure 🤔</b>: If it's unclear, that's totally fine!</p>
        
        <p>4. <b>💬 Optional Critiques</b> If you'd like, you can leave notes to explain your choice or provide helpful feedback. Your insights are gold to us!</p>
        
        <p>5. <b>↔️ Easy Navigation</b> Click the <b>Right Arrow</b> ➡️ to move forward and the <b>Left Arrow</b> ⬅️ to revisit previous entries.</p>
        
        <p>6. <b>📥 All Done? Download & Submit!</b> Once you've reviewed all memories, hit <b>"Download Labelled Data"</b>. Then simply email the file to <b>Ben Field at ben.field@visory.com.au</b>.</p>
        
        <p style='text-align:center;margin-top:20px;'><b>🎉 Thank you for lending your expertise! Together, we're making Delphi even more brilliant! 🎉</b></p>
    """, unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"<h3 style='color:{BRAND_COLOR};'>Navigation Control</h3>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose processed/labeled JSONL file",
        type=["jsonl"],
        key="file_uploader",
        accept_multiple_files=False
    )

    # Removed the filter checkbox as requested

    st.divider()

    # Initialize session state variables robustly
    st.session_state.setdefault('data', [])
    st.session_state.setdefault('all_data', [])
    st.session_state.setdefault('index', 0)
    st.session_state.setdefault('labels', {})
    st.session_state.setdefault('filter_positives', False)  # Kept for compatibility
    st.session_state.setdefault('current_file_id', None)
    st.session_state.setdefault('current_file_name', None)

    # --- Data Loading Logic ---
    if uploaded_file is not None:
        if st.session_state.current_file_id != uploaded_file.file_id:
            # Load data silently without showing technical messages
            loaded_data, loaded_labels = load_data_and_labels(uploaded_file)

            if loaded_data:
                st.session_state.all_data = loaded_data
                st.session_state.labels = loaded_labels
                st.session_state.current_file_id = uploaded_file.file_id
                st.session_state.current_file_name = uploaded_file.name
                apply_filter()
                # No success messages about loading records
            else:
                st.session_state.all_data = []
                st.session_state.data = []
                st.session_state.labels = {}
                st.session_state.current_file_id = None
                st.session_state.current_file_name = None
                st.session_state.index = 0

    elif st.session_state.current_file_id is not None:
        # Silently clear session state
        st.session_state.all_data = []
        st.session_state.data = []
        st.session_state.labels = {}
        st.session_state.current_file_id = None
        st.session_state.current_file_name = None
        st.session_state.index = 0

    # --- Sidebar Navigation ---
    if st.session_state.all_data:
        total_all_records = len(st.session_state.all_data)
        total_filtered_records = len(st.session_state.data)
        current_index = st.session_state.index
        is_filtered = st.session_state.get('filter_positives', False)

        display_total = total_filtered_records if is_filtered else total_all_records

        if current_index >= total_filtered_records:
             current_index = max(0, total_filtered_records - 1)
        if total_filtered_records == 0:
             current_index = 0
        elif current_index < 0:
             current_index = 0
        st.session_state.index = current_index

        record_id = None
        if total_filtered_records > 0:
            record = st.session_state.data[current_index]
            record_id = record.get("observation_id", f"UNKNOWN_ID_{current_index}")

        labeled_ids = set(st.session_state.get('labels', {}).keys())
        labeled_count_total = len(labeled_ids)

        filtered_ids = {r.get("observation_id") for r in st.session_state.data if r.get("observation_id")}
        labeled_count_filtered = len(filtered_ids.intersection(labeled_ids))

        # Stylish progress information
        if is_filtered:
            st.markdown(f"""
                <div style='background-color:rgba(223, 0, 116, 0.05);padding:10px;border-radius:5px;margin-bottom:10px;'>
                    <p style='margin:0;'>Viewing Record: <b>{current_index + 1} / {total_filtered_records}</b> (filtered)</p>
                </div>
            """, unsafe_allow_html=True)
            st.progress((current_index + 1) / total_filtered_records if total_filtered_records > 0 else 0)
            st.markdown(f"""
                <div style='text-align:center;margin-top:5px;'>
                    <p>Labeled: <b>{labeled_count_filtered} / {total_filtered_records}</b> (in filtered view)</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style='background-color:rgba(223, 0, 116, 0.05);padding:10px;border-radius:5px;margin-bottom:10px;'>
                    <p style='margin:0;'>Viewing Record: <b>{current_index + 1} / {total_all_records}</b> (total)</p>
                </div>
            """, unsafe_allow_html=True)
            st.progress((current_index + 1) / total_all_records if total_all_records > 0 else 0)
            st.markdown(f"""
                <div style='text-align:center;margin-top:5px;'>
                    <p>Labeled: <b>{labeled_count_total} / {total_all_records}</b> (total)</p>
                </div>
            """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            prev_disabled = (current_index <= 0)
            st.button(
                "⬅️ Previous",
                use_container_width=True,
                disabled=prev_disabled,
                on_click=go_previous
            )
        with col2:
            next_disabled = (current_index >= total_filtered_records - 1) or (total_filtered_records == 0)
            st.button(
                "Next ➡️",
                use_container_width=True,
                disabled=next_disabled,
                on_click=go_next
            )

        st.divider()

        st.markdown(f"<h3 style='color:{BRAND_COLOR};'>Save Progress</h3>", unsafe_allow_html=True)
        if st.session_state.get('labels'):
            labeled_jsonl_data = generate_labeled_data_jsonl()
            if labeled_jsonl_data:
                st.download_button(
                    label="Download Labeled Data (JSONL)",
                    data=labeled_jsonl_data,
                    file_name=DEFAULT_OUTPUT_FILENAME,
                    mime="application/jsonl",
                    key="download_button"
                )
            else:
                st.caption("No labeled records to download (or error generating data).")
        else:
             st.caption("Label records to enable download.")

    elif not st.session_state.data and st.session_state.all_data:
        # Show a more user-friendly message
        st.markdown(f"""
            <div style='background-color:rgba(223, 0, 116, 0.05);padding:15px;border-radius:5px;margin-bottom:20px;text-align:center;'>
                <p>No records with &lt;MEMORY&gt; tags found in this file.</p>
                <p>Uncheck the filter box to see all records.</p>
            </div>
        """, unsafe_allow_html=True)

    elif not uploaded_file and st.session_state.current_file_id is None:
        st.markdown(f"""
            <div style='background-color:rgba(223, 0, 116, 0.05);padding:20px;border-radius:5px;text-align:center;margin-top:30px;'>
                <p>Upload a processed JSONL file to begin labeling.</p>
                <p style='font-size:0.9rem;color:#666;'>The tool will analyze the file and extract records for your review.</p>
            </div>
        """, unsafe_allow_html=True)

# --- Main Area ---
if st.session_state.data:
    current_index = st.session_state.index
    if 0 <= current_index < len(st.session_state.data):
        record = st.session_state.data[current_index]
        record_id = record.get("observation_id", f"UNKNOWN_ID_{current_index}")

        # Stylish record header
        st.markdown(f"""
            <div style='margin-bottom:20px;'>
                <h3 style='color:{BRAND_COLOR};margin-bottom:5px;'>Record Details</h3>
                <p style='margin:0;'>Record ID: <b>{record_id}</b> | Type: <b>{record.get('alert_type', 'N/A').upper()}</b></p>
            </div>
        """, unsafe_allow_html=True)

        # Enhanced LLM Output box
        st.markdown(f"<h4 style='color:{BRAND_COLOR};'>Delphi's Output:</h4>", unsafe_allow_html=True)
        
        # Style the output box with a light version of the brand color
        output_bg_color = "rgba(223, 0, 116, 0.05)"
        output_border_color = "rgba(223, 0, 116, 0.3)"
        
        if "<MEMORY" in record.get('llm_output', ''):
            # Highlight memory tags in the output with brand color
            output_text = record.get('llm_output', '*No Output Recorded*')
            # Safely replace with HTML highlighting
            output_text = output_text.replace("<MEMORY", f"<span style='color:{BRAND_COLOR};font-weight:bold;'>&lt;MEMORY")
            output_text = output_text.replace("</MEMORY>", f"&lt;/MEMORY&gt;</span>")
            st.markdown(f"""
                <div style='background-color:{output_bg_color};padding:15px;border-radius:5px;border-left:3px solid {output_border_color};'>
                    {output_text}
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style='background-color:{output_bg_color};padding:15px;border-radius:5px;border-left:3px solid {output_border_color};'>
                    {record.get('llm_output', '*No Output Recorded*')}
                </div>
            """, unsafe_allow_html=True)

        # Stylish expandable sections
        with st.expander("View System Prompt"):
            st.code(record.get('system_prompt', 'N/A'), language=None)

        col_meta, col_mem = st.columns(2)
        with col_meta:
            with st.expander("View Chat Metadata", expanded=False):
                st.json(record.get('chat_metadata', {}))
        with col_mem:
            with st.expander(f"View Existing Memories ({len(record.get('existing_memories',[]))})", expanded=False):
                 memories = record.get('existing_memories', [])
                 if memories:
                     for mem in memories:
                          ts_str = mem.get('createdAt', '')
                          ts_readable = ts_str
                          if ts_str:
                               try:
                                    dt_obj = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                    ts_readable = dt_obj.strftime(READABLE_TIMESTAMP_FORMAT)
                               except ValueError:
                                    pass
                          st.markdown(f"""
                              <div style='margin-bottom:8px;padding:5px;border-left:2px solid {BRAND_COLOR};padding-left:10px;'>
                                  <code>{mem.get('memory', 'N/A')}</code>
                                  <div style='font-size:0.8rem;color:#666;'>
                                      Card: {mem.get('cardId')}, Reply: {mem.get('replyId', 'N/A')}, Time: {ts_readable}
                                  </div>
                              </div>
                          """, unsafe_allow_html=True)
                 else:
                      st.write("None")

        # Enhanced chat history display
        st.markdown(f"<h4 style='color:{BRAND_COLOR};'>Chat History:</h4>", unsafe_allow_html=True)
        chat_display_area = st.container(height=400, border=True)
        formatted_history = format_chat_history(record.get('chat_history', []))
        for line in formatted_history:
            chat_display_area.markdown(line, unsafe_allow_html=True)

        st.divider()

        # --- Stylish Labeling Inputs with simplified options ---
        st.markdown(f"<h3 style='color:{BRAND_COLOR};'>Your Assessment</h3>", unsafe_allow_html=True)

        existing_labels = st.session_state.get('labels', {}).get(record_id, {})
        try:
            classification = existing_labels.get("human_label_classification", LABEL_CLASSIFICATIONS[-1])
            current_classification_index = LABEL_CLASSIFICATIONS.index(classification)
        except ValueError:
            current_classification_index = len(LABEL_CLASSIFICATIONS) - 1
            st.warning(f"Invalid label '{classification}' found for record {record_id}. Resetting to 'I'm not sure 🤔'.")

        st.radio(
            "**How did Delphi do?**",
            options=LABEL_CLASSIFICATIONS,
            key=f"label_classification_{record_id}",
            index=current_classification_index,
            horizontal=True,
            on_change=save_labels_to_state,
            args=(current_index, record_id)
        )

        st.text_area(
            "**Optional:** Correct Memory Text (If you think there's a better version)",
            key=f"correct_mem_{record_id}",
            value=existing_labels.get("human_label_correct_memory_optional", ""),
            height=None,
            help="If Delphi missed something, what would have been the correct <MEMORY> tag?",
            on_change=save_labels_to_state,
            args=(current_index, record_id)
        )

        # Critique text area with brand-colored border
        st.markdown(f"""
            <style>
                div[data-testid="stTextArea"] textarea {{
                    border-left: 2px solid {BRAND_COLOR} !important;
                }}
            </style>
        """, unsafe_allow_html=True)
        
        st.text_area(
            "Your Feedback (Any additional thoughts or explanations)",
            key=f"critique_{record_id}",
            value=existing_labels.get("human_label_critique", ""),
            height=100,
            on_change=save_labels_to_state,
            args=(current_index, record_id)
        )
        
        # Add a subtle branded footer to each record view
        st.markdown(f"""
            <div style='text-align:center;margin-top:30px;padding-top:10px;border-top:1px solid #eee;'>
                <p style='color:#666;font-size:0.8rem;'>
                    Visory AI Alert Labeling Tool | <span style='color:{BRAND_COLOR};'>Your feedback improves our system</span>
                </p>
            </div>
        """, unsafe_allow_html=True)
