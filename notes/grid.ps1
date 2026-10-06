$label = $args[0]
foreach ($r in 1000, 2000, 3000, 4000, 5000) {
    $out = & .\START.cmd tournament my-team --against balanced --seeds "$r..$($r + 20)" 2>&1
    $rec = ($out | Select-String 'record').Line.Trim()
    $gl  = ($out | Select-String 'goals').Line.Trim()
    $gd  = ($out | Select-String 'goal diff').Line.Trim()
    "$label range $r : $rec : $gl : $gd"
}
