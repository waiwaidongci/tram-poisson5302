from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def run(item, detail=False):
    item_view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
                 'author': item.author, 'review': item.review, 'decision': item.decision,
                 'created_at': iso(item.created_at), 'finished_at': iso(item.finished_at),
                 'scheduled_at': iso(item.scheduled_at), 'schedule_id': item.schedule_id,
                 'has_export': bool(item.export_file), 'error': item.error}
    if detail:
        item_view.update(params=item.params, result=item.result, review_note=item.review_note)
    return item_view


def schedule(item):
    from src.domain.spec import SPEC
    return {'id': item.id, 'name': item.name, 'dataset_id': item.dataset_id, 'recipient': item.recipient,
            'next_at': iso(item.next_at), 'repeat_daily': item.repeat_daily, 'enabled': item.enabled,
            'next_report_day': item.params.get(SPEC['schedule_date_param']) if item.enabled else None}


def delivery(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'state': item.state, 'detail': item.detail, 'created_at': iso(item.created_at)}


def experiment(item, detail=False):
    view = {'id': item.id, 'name': item.name, 'status': item.status,
            'pair_count': item.pair_count, 'included_count': item.included_count,
            'warmup_minutes': item.warmup_minutes, 'permutations': item.permutations,
            'has_recon': item.recon_rows is not None,
            'recon_checksum': item.recon_checksum, 'draw_checksum': item.draw_checksum,
            'author': item.author, 'error': item.error,
            'created_at': iso(item.created_at), 'updated_at': iso(item.updated_at),
            'computed_at': iso(item.computed_at)}
    if detail:
        view.update(draw_rows=item.draw_rows, result=item.result)
    return view


def conclusion(item):
    return {'id': item.id, 'experiment_id': item.experiment_id, 'version': item.version,
            'state': item.state, 'reason': item.reason, 'author': item.author,
            'draw_checksum': item.draw_checksum, 'recon_checksum': item.recon_checksum,
            'created_at': iso(item.created_at), 'superseded_at': iso(item.superseded_at),
            'headline': item.result.get('headline'),
            'observed_difference': item.result['stats']['observed_difference'],
            'p_value': item.result['stats']['p_value'],
            'included_pairs': item.result['stats']['included_pairs'],
            'excluded_pairs': item.result['stats']['excluded_pairs']}
