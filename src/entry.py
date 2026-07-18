"""

 OMRChecker

 Author: Udayraj Deshmukh
 Github: https://github.com/Udayraj123

"""
import os
from csv import QUOTE_NONNUMERIC
from pathlib import Path
from time import time

import cv2
import pandas as pd
from rich.table import Table

from src.constants.common import (
    CONFIG_FILENAME,
    ERROR_CODES,
    EVALUATION_FILENAME,
    TEMPLATE_FILENAME,
)
from src.defaults import CONFIG_DEFAULTS
from src.evaluation import EvaluationConfig, evaluate_concatenated_response
from src.logger import console, logger
from src.template import Template
from src.utils.file import Paths, setup_dirs_for_paths, setup_outputs_for_template
from src.utils.image import ImageUtils
from src.utils.interaction import InteractionUtils, Stats
from src.utils.parsing import get_concatenated_response, open_config_with_defaults

# Load processors
STATS = Stats()


def entry_point(input_dir, args):
    if not os.path.exists(input_dir):
        raise Exception(f"Given input directory does not exist: '{input_dir}'")
    curr_dir = input_dir
    return process_dir(input_dir, curr_dir, args)


def print_config_summary(
    curr_dir,
    omr_files,
    template,
    tuning_config,
    local_config_path,
    evaluation_config,
    args,
):
    logger.info("")
    table = Table(title="Current Configurations", show_header=False, show_lines=False)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")
    table.add_row("Directory Path", f"{curr_dir}")
    table.add_row("Count of Images", f"{len(omr_files)}")
    table.add_row("Set Layout Mode ", "ON" if args["setLayout"] else "OFF")
    pre_processor_names = [pp.__class__.__name__ for pp in template.pre_processors]
    table.add_row(
        "Markers Detection",
        "ON" if "CropOnMarkers" in pre_processor_names else "OFF",
    )
    table.add_row("Auto Alignment", f"{tuning_config.alignment_params.auto_align}")
    table.add_row("Detected Template Path", f"{template}")
    if local_config_path:
        table.add_row("Detected Local Config", f"{local_config_path}")
    if evaluation_config:
        table.add_row("Detected Evaluation Config", f"{evaluation_config}")

    table.add_row(
        "Detected pre-processors",
        ", ".join(pre_processor_names),
    )
    console.print(table, justify="center")


def process_dir(
    root_dir,
    curr_dir,
    args,
    template=None,
    tuning_config=CONFIG_DEFAULTS,
    evaluation_config=None,
):
    # Update local tuning_config (in current recursion stack)
    local_config_path = curr_dir.joinpath(CONFIG_FILENAME)
    if os.path.exists(local_config_path):
        tuning_config = open_config_with_defaults(local_config_path)

    # Update local template (in current recursion stack)
    local_template_path = curr_dir.joinpath(TEMPLATE_FILENAME)
    local_template_exists = os.path.exists(local_template_path)
    if local_template_exists:
        template = Template(
            local_template_path,
            tuning_config,
        )
    # Look for subdirectories for processing
    subdirs = [d for d in curr_dir.iterdir() if d.is_dir()]

    output_dir = Path(args["output_dir"], curr_dir.relative_to(root_dir))
    paths = Paths(output_dir)

    # look for images in current dir to process
    exts = ("*.[pP][nN][gG]", "*.[jJ][pP][gG]", "*.[jJ][pP][eE][gG]", "*.[pP][dD][fF]")
    omr_files = sorted([f for ext in exts for f in curr_dir.glob(ext)])

    # Exclude images (take union over all pre_processors)
    excluded_files = []
    if template:
        for pp in template.pre_processors:
            excluded_files.extend(Path(p) for p in pp.exclude_files())

    local_evaluation_path = curr_dir.joinpath(EVALUATION_FILENAME)
    if not args["setLayout"] and os.path.exists(local_evaluation_path):
        if not local_template_exists:
            logger.warning(
                f"Found an evaluation file without a parent template file: {local_evaluation_path}"
            )
        evaluation_config = EvaluationConfig(
            curr_dir,
            local_evaluation_path,
            template,
            tuning_config,
        )

        excluded_files.extend(
            Path(exclude_file) for exclude_file in evaluation_config.get_exclude_files()
        )

    omr_files = [f for f in omr_files if f not in excluded_files]

    if omr_files:
        if not template:
            logger.error(
                f"Found images, but no template in the directory tree \
                of '{curr_dir}'. \nPlace {TEMPLATE_FILENAME} in the \
                appropriate directory."
            )
            raise Exception(
                f"No template file found in the directory tree of {curr_dir}"
            )

        setup_dirs_for_paths(paths)
        outputs_namespace = setup_outputs_for_template(paths, template)

        print_config_summary(
            curr_dir,
            omr_files,
            template,
            tuning_config,
            local_config_path,
            evaluation_config,
            args,
        )
        if args["setLayout"]:
            show_template_layouts(omr_files, template, tuning_config, outputs_namespace)
        else:
            process_files(
                omr_files,
                template,
                tuning_config,
                evaluation_config,
                outputs_namespace,
            )

    elif not subdirs:
        # Each subdirectory should have images or should be non-leaf
        logger.info(
            f"No valid images or sub-folders found in {curr_dir}.\
            Empty directories not allowed."
        )

    # recursively process sub-folders
    for d in subdirs:
        process_dir(
            root_dir,
            d,
            args,
            template,
            tuning_config,
            evaluation_config,
        )



def show_template_layouts(omr_files, template, tuning_config, outputs_namespace):
    for file_path in omr_files:
        images = ImageUtils.load_omr_image(file_path, tuning_config)
        for img_name, in_omr in images:
            in_omr = template.image_instance_ops.apply_preprocessors(
                str(file_path), in_omr, template
            )
            if in_omr is None:
                new_file_path = outputs_namespace.paths.errors_dir.joinpath(img_name)
                outputs_namespace.OUTPUT_SET.append(
                    [img_name] + outputs_namespace.empty_resp
                )
                if check_and_move(ERROR_CODES.NO_MARKER_ERR, file_path, new_file_path):
                    err_line = [
                        img_name,
                        file_path,
                        new_file_path,
                        "NA",
                    ] + outputs_namespace.empty_resp
                    pd.DataFrame(err_line, dtype=str).T.to_csv(
                        outputs_namespace.files_obj["Errors"],
                        mode="a",
                        quoting=QUOTE_NONNUMERIC,
                        header=False,
                        index=False,
                    )
                continue
            template_layout = template.image_instance_ops.draw_template_layout(
                in_omr, template, shifted=False, border=2
            )
            InteractionUtils.show(
                f"Template Layout: {img_name}", template_layout, 1, 1, config=tuning_config
            )


def _process_single_image(
    file_path,
    img_name,
    in_omr,
    template,
    tuning_config,
    evaluation_config,
    outputs_namespace,
    files_counter,
):
    logger.info("")
    logger.info(
        f"({files_counter}) Opening image: \t'{img_name}'\tResolution: {in_omr.shape}"
    )

    template.image_instance_ops.reset_all_save_img()

    template.image_instance_ops.append_save_img(1, in_omr)

    in_omr = template.image_instance_ops.apply_preprocessors(
        img_name, in_omr, template
    )

    if in_omr is None:
        # Error OMR case
        new_file_path = outputs_namespace.paths.errors_dir.joinpath(img_name)
        outputs_namespace.OUTPUT_SET.append(
            [img_name] + outputs_namespace.empty_resp
        )
        if check_and_move(ERROR_CODES.NO_MARKER_ERR, file_path, new_file_path):
            err_line = [
                img_name,
                file_path,
                new_file_path,
                "NA",
            ] + outputs_namespace.empty_resp
            pd.DataFrame(err_line, dtype=str).T.to_csv(
                outputs_namespace.files_obj["Errors"],
                mode="a",
                quoting=QUOTE_NONNUMERIC,
                header=False,
                index=False,
            )
        return None

    # uniquify
    file_id = str(img_name)
    save_dir = outputs_namespace.paths.save_marked_dir
    (
        response_dict,
        final_marked,
        multi_marked,
        _,
    ) = template.image_instance_ops.read_omr_response(
        template, image=in_omr, name=file_id, save_dir=save_dir
    )

    # TODO: move inner try catch here
    # concatenate roll nos, set unmarked responses, etc
    omr_response = get_concatenated_response(response_dict, template)

    if (
        evaluation_config is None
        or not evaluation_config.get_should_explain_scoring()
    ):
        logger.info(f"Read Response: \n{omr_response}")

    score = 0
    if evaluation_config is not None:
        score = evaluate_concatenated_response(
            omr_response,
            evaluation_config,
            Path(img_name),
            outputs_namespace.paths.evaluation_dir,
        )
        logger.info(
            f"(/{files_counter}) Graded with score: {round(score, 2)}\t for file: '{file_id}'"
        )
    else:
        logger.info(f"(/{files_counter}) Processed file: '{file_id}'")

    if tuning_config.outputs.show_image_level >= 2:
        InteractionUtils.show(
            f"Final Marked Bubbles : '{file_id}'",
            ImageUtils.resize_util_h(
                final_marked, int(tuning_config.dimensions.display_height * 1.3)
            ),
            1,
            1,
            config=tuning_config,
        )

    resp_array = []
    for k in template.output_columns:
        resp_array.append(omr_response[k])

    if img_name.startswith("page_1."):
        # Set Roll_no to "KEY"
        if "Roll_no" in template.output_columns:
            idx = template.output_columns.index("Roll_no")
            resp_array[idx] = "KEY"
        img_name = "Answer Key"

    outputs_namespace.OUTPUT_SET.append([img_name] + resp_array)

    if multi_marked == 0 or not tuning_config.outputs.filter_out_multimarked_files:
        STATS.files_not_moved += 1
        new_file_path = save_dir.joinpath(file_id)
        # Enter into Results sheet-
        results_line = [img_name, file_path, new_file_path, score] + resp_array
        # Write/Append to results_line file(opened in append mode)
        pd.DataFrame(results_line, dtype=str).T.to_csv(
            outputs_namespace.files_obj["Results"],
            mode="a",
            quoting=QUOTE_NONNUMERIC,
            header=False,
            index=False,
        )
    else:
        # multi_marked file
        logger.info(f"[{files_counter}] Found multi-marked file: '{file_id}'")
        new_file_path = outputs_namespace.paths.multi_marked_dir.joinpath(img_name)
        if check_and_move(ERROR_CODES.MULTI_BUBBLE_WARN, file_path, new_file_path):
            mm_line = [img_name, file_path, new_file_path, "NA"] + resp_array
            pd.DataFrame(mm_line, dtype=str).T.to_csv(
                outputs_namespace.files_obj["MultiMarked"],
                mode="a",
                quoting=QUOTE_NONNUMERIC,
                header=False,
                index=False,
            )

    return multi_marked


def process_files(
    omr_files,
    template,
    tuning_config,
    evaluation_config,
    outputs_namespace,
):
    start_time = int(time())
    files_counter = 0
    STATS.files_not_moved = 0

    # 1. Parse the first page of the PDF (the teacher's key sheet) to get the answer key
    if omr_files and evaluation_config is not None:
        key_file = omr_files[0]
        logger.info(f"Extracting answer key from first page: {key_file.name}")
        try:
            images = ImageUtils.load_omr_image(key_file, tuning_config)
            for img_name, in_omr in images:
                in_omr_preprocessed = template.image_instance_ops.apply_preprocessors(
                    img_name, in_omr, template
                )
                if in_omr_preprocessed is not None:
                    response_dict, _, _, _ = template.image_instance_ops.read_omr_response(
                        template, image=in_omr_preprocessed, name=str(img_name), save_dir=None
                    )
                    key_response = get_concatenated_response(response_dict, template)
                    
                    # Update evaluation_config answer key with these parsed answers
                    parsed_answers = []
                    for q in evaluation_config.questions_in_order:
                        ans = key_response.get(q, "")
                        parsed_answers.append(ans)
                        
                    evaluation_config.question_to_answer_matcher = evaluation_config.parse_answers_and_map_questions(
                        parsed_answers
                    )
                    logger.info(f"Successfully loaded answer key from first page: {key_response}")
                    
                    # Also write these parsed answers to answer_key.csv in the input directory
                    csv_path = Path(evaluation_config.path).parent.joinpath("answer_key.csv")
                    with open(csv_path, 'w') as f:
                        for q in evaluation_config.questions_in_order:
                            ans = key_response.get(q, "")
                            f.write(f"{q},{ans}\n")
                    logger.info(f"Saved parsed answer key to {csv_path}")
        except Exception as e:
            logger.error(f"Failed to automatically extract answer key from first page: {e}")

    # Collect names from non-PDF files to detect collisions
    image_file_names = {f.name for f in omr_files if f.suffix.lower() != ".pdf"}

    for file_path in omr_files:
        images = ImageUtils.load_omr_image(file_path, tuning_config)
        for img_name, in_omr in images:
            if file_path.suffix.lower() == ".pdf" and img_name in image_file_names:
                logger.warning(
                    f"PDF page name '{img_name}' collides with an existing image file, output may be overwritten."
                )
            files_counter += 1
            _process_single_image(
                file_path,
                img_name,
                in_omr,
                template,
                tuning_config,
                evaluation_config,
                outputs_namespace,
                files_counter,
            )

    print_stats(start_time, files_counter, tuning_config)
    generate_option_analysis(outputs_namespace, template, evaluation_config)


def generate_option_analysis(outputs_namespace, template, evaluation_config):
    results_csv_path = outputs_namespace.filesMap.get("Results")
    if not results_csv_path or not os.path.exists(results_csv_path):
        logger.warning("Results CSV path not found, skipping option analysis.")
        return
        
    try:
        df = pd.read_csv(results_csv_path)
        if len(df) == 0:
            logger.info("Results CSV is empty, skipping option analysis.")
            return
            
        student_df = df.copy()
        if "page_1.png" in student_df["file_id"].values and "page_2.png" in student_df["file_id"].values:
            student_df = student_df[student_df["file_id"] != "page_1.png"]
        student_df = student_df[~student_df["file_id"].astype(str).str.contains("key", case=False)]
        
        if len(student_df) == 0:
            logger.info("No student sheets found in Results, skipping option analysis.")
            return
            
        analysis_rows = []
        for q in template.output_columns:
            if not (q.startswith("q") and q[1:].isdigit()):
                continue
            if q not in student_df.columns:
                continue
                
            correct_ans = ""
            if evaluation_config and q in evaluation_config.question_to_answer_matcher:
                matcher = evaluation_config.question_to_answer_matcher[q]
                correct_ans = str(matcher.answer_item)
                
            col_data = student_df[q].fillna("").astype(str).str.strip().str.upper()
            
            count_a = sum(col_data == "A")
            count_b = sum(col_data == "B")
            count_c = sum(col_data == "C")
            count_d = sum(col_data == "D")
            count_unmarked = sum(col_data == "")
            count_multiple = sum(col_data.str.len() > 1)
            total_students = len(col_data)
            
            correct_count = 0
            incorrect_count = 0
            unmarked_count = 0
            
            for val in col_data:
                if val == "":
                    unmarked_count += 1
                elif evaluation_config and q in evaluation_config.question_to_answer_matcher:
                    matcher = evaluation_config.question_to_answer_matcher[q]
                    verdict, _ = matcher.get_verdict_marking(val)
                    if verdict.startswith("correct"):
                        correct_count += 1
                    elif verdict == "unmarked":
                        unmarked_count += 1
                    else:
                        incorrect_count += 1
                else:
                    incorrect_count += 1
                    
            pct_correct = f"{(correct_count / total_students * 100):.2f}%" if total_students > 0 else "0.00%"
            
            analysis_rows.append({
                "Question": q,
                "Correct Answer": correct_ans,
                "A Count": count_a,
                "B Count": count_b,
                "C Count": count_c,
                "D Count": count_d,
                "Multiple Count": count_multiple,
                "Unmarked Count": count_unmarked,
                "Total Students": total_students,
                "Correct Count": correct_count,
                "Incorrect Count": incorrect_count,
                "Percent Correct": pct_correct
            })
            
        analysis_df = pd.DataFrame(analysis_rows)
        option_analysis_csv_path = outputs_namespace.paths.results_dir.joinpath("Option_Analysis.csv")
        analysis_df.to_csv(option_analysis_csv_path, index=False)
        logger.info(f"Generated Option Analysis report at: '{option_analysis_csv_path}'")
        
    except Exception as e:
        logger.error(f"Error generating option analysis: {e}")


def check_and_move(error_code, file_path, filepath2):
    # TODO: fix file movement into error/multimarked/invalid etc again
    STATS.files_not_moved += 1
    return True


def print_stats(start_time, files_counter, tuning_config):
    time_checking = max(1, round(time() - start_time, 2))
    log = logger.info
    log("")
    log(f"{'Total file(s) moved': <27}: {STATS.files_moved}")
    log(f"{'Total file(s) not moved': <27}: {STATS.files_not_moved}")
    log("--------------------------------")
    log(
        f"{'Total file(s) processed': <27}: {files_counter} ({'Sum Tallied!' if files_counter == (STATS.files_moved + STATS.files_not_moved) else 'Not Tallying!'})"
    )

    if tuning_config.outputs.show_image_level <= 0:
        log(
            f"\nFinished Checking {files_counter} file(s) in {round(time_checking, 1)} seconds i.e. ~{round(time_checking / 60, 1)} minute(s)."
        )
        log(
            f"{'OMR Processing Rate': <27}: \t ~ {round(time_checking / files_counter, 2)} seconds/OMR"
        )
        log(
            f"{'OMR Processing Speed': <27}: \t ~ {round((files_counter * 60) / time_checking, 2)} OMRs/minute"
        )
    else:
        log(f"\n{'Total script time': <27}: {time_checking} seconds")

    if tuning_config.outputs.show_image_level <= 1:
        log(
            "\nTip: To see some awesome visuals, open config.json and increase 'show_image_level'"
        )
