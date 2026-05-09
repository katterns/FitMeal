from prometheus_client import Counter

ANALYSIS_CREATED = Counter(
    "fitmeal_analysis_created_total",
    "Задачи анализа, принятые API и отправленные в очередь",
    ["tier"],
)

ANALYSIS_FINISHED = Counter(
    "fitmeal_analysis_finished_total",
    "Задачи анализа, завершённые в worker",
    ["tier", "status"],
)

ANALYSIS_REJECTED = Counter(
    "fitmeal_analysis_rejected_total",
    "Отказ до постановки в очередь (POST /analysis)",
    ["tier", "reason"],
)
