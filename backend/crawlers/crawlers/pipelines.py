import json


class JsonLinesWriter:
    """Buffers items to a file. The file name comes in as a spider argument
    (out_file=...), so invocation stays shell-friendly and the task that
    launched the spider owns reading the file back."""

    def open_spider(self, spider):
        self._file = open(spider.out_file, "w", encoding="utf-8")

    def close_spider(self, spider):
        self._file.close()

    def process_item(self, item, spider):
        row = dict(item)
        # dates come out as python objects from the spiders; keep them JSON safe
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
        return item