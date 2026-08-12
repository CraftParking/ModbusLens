# Per-function max block size a merged read is allowed to grow to -- Modbus spec
# maximums, matching register_scanner.py's own _MAX_BLOCK and the per-tag counts
# _validate_tag_request already enforces before a tag ever reaches here (so a single
# already-validated tag can never exceed these on its own; a merged block only ever
# needs to fit two or more of them together).
_MAX_BLOCK = {
    "Coil": 2000,
    "Discrete Input": 2000,
    "Holding Register": 125,
    "Input Register": 125,
}


def merge_tag_reads(tags, offset_of):
    """Group Read-mode tags into the fewest possible wire requests, one per
    contiguous/overlapping run of same-type address ranges -- mirrors ModbusTools'
    createReadMessages. Deliberately zero gap tolerance: a block is only ever the exact
    union of its member tags' own [start, end] ranges (merges when the next tag's range
    touches or overlaps the block so far, never when there's a gap), so this can never
    read a register no tag actually asked for. A run that would exceed its function's
    max block size splits into more than one block instead.

    `tags` must already be Read-mode and individually address/count-validated -- this
    does no validation of its own, just grouping. `offset_of(tag)` computes the tag's
    protocol offset (pure, no I/O).

    Returns a list of plans, one wire request each:
      {"type": tag_type, "start": offset, "count": n,
       "members": [(tag, local_offset), ...]}
    `local_offset` is the index into that block's own returned value list where the
    member tag's data begins, so the caller can slice each tag's values back out."""
    by_type = {}
    for tag in tags:
        start = offset_of(tag)
        end = start + tag["count"] - 1
        by_type.setdefault(tag["type"], []).append((start, end, tag))

    plans = []
    for tag_type, entries in by_type.items():
        entries.sort(key=lambda entry: entry[0])
        max_block = _MAX_BLOCK.get(tag_type, 125)
        block = None  # {"start": int, "end": int, "members": [(tag, start), ...]}
        for start, end, tag in entries:
            fits_current_block = (
                block is not None
                and start <= block["end"] + 1
                and (max(block["end"], end) - block["start"] + 1) <= max_block
            )
            if fits_current_block:
                block["end"] = max(block["end"], end)
                block["members"].append((tag, start))
            else:
                if block is not None:
                    plans.append(_finalize_block(tag_type, block))
                block = {"start": start, "end": end, "members": [(tag, start)]}
        if block is not None:
            plans.append(_finalize_block(tag_type, block))
    return plans


def _finalize_block(tag_type, block):
    block_start = block["start"]
    return {
        "type": tag_type,
        "start": block_start,
        "count": block["end"] - block_start + 1,
        "members": [(tag, start - block_start) for tag, start in block["members"]],
    }
