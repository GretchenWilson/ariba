import pymummer

columns = [
    'ref_name',              # 0  name of reference sequence
    'ref_type',              # 1  type of reference sequence (presence/absence, variants only, noncoding)
    'flag',                  # 2  cluster flag
    'reads',                 # 3  number of reads in this cluster
    'cluster_rep',           # 4  name of cluster representitive from cd hit
    'ref_len',               # 5  length of reference sequence
    'ref_base_assembled',    # 6  number of reference nucleotides assembled by this contig
    'pc_ident',              # 7  %identity between ref sequence and contig
    'ctg',                   # 8  name of contig matching reference
    'ctg_len',               # 9  length of contig matching reference
    'known_var',             # 10 is this a known SNP from reference metadata? 1|0
    'var_type',              # 11 The type of variant. Currently only SNP supported
    'var_seq_type',          # 12 if known_var=1, n|p for nucleotide or protein
    'known_var_change',      # 13 if known_var=1, the wild/variant change, eg I42L
    'has_known_var',         # 13 if known_var=1, 1|0 for whether or not the assembly has the variant
    'ref_ctg_change',        # 14 amino acid or nucleotide change between reference and contig, eg I42L
    'ref_ctg_effect',        # 15 effect of change between reference and contig, eg SYS, NONSYN (amino acid changes only)
    'ref_start',             # 16 start position of variant in contig
    'ref_end',               # 17 end position of variant in contig
    'ref_nt',                # 18 nucleotide(s) in contig at variant position
    'ctg_start',             # 19 start position of variant in contig
    'ctg_end',               # 20 end position of variant in contig
    'ctg_nt',                # 21 nucleotide(s) in contig at variant position
    'smtls_total_depth',     # 22 total read depth at variant start position in contig, reported by mpileup
    'smtls_alt_nt',          # 23 alt nucleotides on contig, reported by mpileup
    'smtls_alt_depth',       # 24 alt depth on contig, reported by mpileup
    'var_description',       # 25 description of variant from reference metdata
    'free_text',             # 26 other free text about reference sequence, from reference metadata
]


def header_line():
    return '\t'.join(columns)


def _samtools_depths_at_known_snps_all_wild(sequence_meta, contig_name, cluster, variant_list):
    '''Input is a known variants, as sequence_metadata object. The
       assumption is that both the reference and the assembly have the
       variant type, not wild type. The list variant_list should be a list
       of pymummer.variant.Variant objects, only contaning variants to the
       relevant query contig'''
    ref_nuc_range = sequence_meta.variant.nucleotide_range()

    if ref_nuc_range is None:
        return None

    depths = []
    ctg_nts = []
    ref_nts = []
    smtls_total_depths = []
    smtls_alt_nts = []
    smtls_alt_depths = []
    contig_positions = []

    for ref_position in range(ref_nuc_range[0], ref_nuc_range[1]+1, 1):
        nucmer_match = cluster.assembly_compare.nucmer_hit_containing_reference_position(cluster.assembly_compare.nucmer_hits, cluster.ref_sequence.id, ref_position)

        if nucmer_match is not None:
            # work out contig position. Needs indels variants to correct the position
            ref_nts.append(cluster.ref_sequence[ref_position])
            contig_position, in_indel = nucmer_match.qry_coords_from_ref_coord(ref_position, variant_list)
            contig_positions.append(contig_position)
            ref, alt, total_depth, alt_depths = cluster.samtools_vars.get_depths_at_position(contig_name, contig_position)
            ctg_nts.append(ref)
            smtls_alt_nts.append(alt)
            smtls_total_depths.append(total_depth)
            smtls_alt_depths.append(alt_depths)

    ctg_nts = ';'.join(ctg_nts) if len(ctg_nts) else '.'
    ref_nts = ';'.join(ref_nts) if len(ref_nts) else '.'
    smtls_alt_nts = ';'.join(smtls_alt_nts) if len(smtls_alt_nts) else '.'
    smtls_total_depths = ';'.join([str(x)for x in smtls_total_depths]) if len(smtls_total_depths) else '.'
    smtls_alt_depths = ';'.join([str(x)for x in smtls_alt_depths]) if len(smtls_alt_depths) else '.'
    ctg_start = str(min(contig_positions) + 1) if contig_positions is not None else '.'
    ctg_end = str(max(contig_positions) + 1) if contig_positions is not None else '.'

    return [str(x) for x in [
        ref_nuc_range[0] + 1,
        ref_nuc_range[1] + 1,
        ref_nts,
        ctg_start,
        ctg_end,
        ctg_nts,
        smtls_total_depths,
        smtls_alt_nts,
        smtls_alt_depths
    ]]


def _report_lines_for_one_contig(cluster, contig_name, ref_cov_per_contig, pymummer_variants):
    lines = []

    common_first_columns = [
        cluster.ref_sequence.id,
        cluster.ref_sequence_type,
        str(cluster.status_flag),
        str(cluster.total_reads),
        cluster.name,
        str(len(cluster.ref_sequence)),
        str(ref_cov_per_contig[contig_name]) if contig_name in ref_cov_per_contig else '0', # 6 ref bases assembled
        str(cluster.assembly_compare.percent_identities[contig_name]) if contig_name in cluster.assembly_compare.percent_identities else '0',
        contig_name,
        str(len(cluster.assembly.sequences[contig_name])),  # 9 length of scaffold matching reference
    ]

    if cluster.ref_sequence.id in cluster.refdata.metadata and  len(cluster.refdata.metadata[cluster.ref_sequence.id]['.']) > 0:
        free_text_columns = [x.free_text for x in cluster.refdata.metadata[cluster.ref_sequence.id]['.']]
    else:
        free_text_columns = ['.']

    if cluster.assembled_ok and contig_name in cluster.assembly_variants and len(cluster.assembly_variants[contig_name]) > 0:
        for (position, var_seq_type, ref_ctg_change, var_effect, contributing_vars, matching_vars_set, metainfo_set) in cluster.assembly_variants[contig_name]:
            if len(matching_vars_set) > 0:
                is_known_var = '1'
                known_var_change = 'unknown'
                var_type = 'SNP'
                has_known_var = '1'
                matching_vars_column = ';;;'.join([x.to_string(separator='_') for x in matching_vars_set])
            else:
                is_known_var = '0'
                known_var_change = '.'
                has_known_var = '0'
                var_type = '.'
                matching_vars_column = '.'

            var_columns = ['.' if x is None else str(x) for x in [is_known_var, var_type, var_seq_type, known_var_change, has_known_var, ref_ctg_change, var_effect]]

            if var_effect not in ['.', 'SYN']:
                cluster.status_flag.add('has_nonsynonymous_variants')

            if contributing_vars is None:
                samtools_columns = [['.'] * 9]
            else:
                contributing_vars.sort(key = lambda x: x.qry_start)

                smtls_total_depth = []
                smtls_alt_nt = []
                smtls_alt_depth = []

                for var in contributing_vars:
                    depths_tuple = cluster.samtools_vars.get_depths_at_position(contig_name, var.qry_start)
                    if depths_tuple is not None:
                        smtls_alt_nt.append(depths_tuple[1])
                        smtls_total_depth.append(str(depths_tuple[2]))
                        smtls_alt_depth.append(str(depths_tuple[3]))

                smtls_total_depth = ';'.join(smtls_total_depth) if len(smtls_total_depth) else '.'
                smtls_alt_nt = ';'.join(smtls_alt_nt) if len(smtls_alt_nt) else '.'
                smtls_alt_depth = ';'.join(smtls_alt_depth) if len(smtls_alt_depth) else '.'
                samtools_columns = [
                        str(contributing_vars[0].ref_start), #ref_start
                        str(contributing_vars[0].ref_end), # ref_end
                        ';'.join([x.ref_base for x in contributing_vars]), # ref_nt
                        str(contributing_vars[0].qry_start),  # ctg_start
                        str(contributing_vars[0].qry_end),  #ctg_end
                        ';'.join([x.qry_base for x in contributing_vars]), #ctg_nt
                        smtls_total_depth,
                        smtls_alt_nt,
                        smtls_alt_depth,
                ]


            if len(matching_vars_set) > 0:
                for matching_var in matching_vars_set:
                    if contributing_vars is None:
                        samtools_columns = _samtools_depths_at_known_snps_all_wild(matching_var, contig_name, cluster, pymummer_variants)
                    var_columns[3] = str(matching_var.variant)

                    if matching_var.has_variant(cluster.ref_sequence) == (ref_ctg_change is not None):
                        var_columns[4] = '0'
                    else:
                        var_columns[4] = '1'

                    if samtools_columns is None:
                        samtools_columns = [['.'] * 9]

                    lines.append('\t'.join(common_first_columns + var_columns + samtools_columns + [matching_vars_column] + free_text_columns))
            else:
                lines.append('\t'.join(
                    common_first_columns + var_columns + \
                    samtools_columns + \
                    [matching_vars_column] + free_text_columns
                ))
    else:
        lines.append('\t'.join(common_first_columns + ['.'] * (len(columns) - len(common_first_columns) - 1) + free_text_columns))

    return lines


def report_lines(cluster):
    if cluster.status_flag.has('ref_seq_choose_fail'):
        return ['\t'.join(['.', '.', str(cluster.status_flag), str(cluster.total_reads), cluster.name] + ['.'] * (len(columns) - 5))]
    elif cluster.status_flag.has('assembly_fail'):
        return ['\t'.join([cluster.ref_sequence.id, cluster.ref_sequence_type, str(cluster.status_flag), str(cluster.total_reads), cluster.name] + ['.'] * (len(columns) - 5))]


    ref_cov_per_contig = cluster.assembly_compare.ref_cov_per_contig(cluster.assembly_compare.nucmer_hits)
    lines = []
    pymummer_variants = pymummer.snp_file.get_all_variants(cluster.assembly_compare.nucmer_snps_file)

    for contig_name in sorted(cluster.assembly.sequences):
        contig_pymummer_variants = [x for x in pymummer_variants if x.qry_name == contig_name]
        lines.extend(_report_lines_for_one_contig(cluster, contig_name, ref_cov_per_contig, contig_pymummer_variants))

    for line in lines:
        assert len(line.split('\t')) == len(columns)

    return lines if len(lines) > 0 else None

