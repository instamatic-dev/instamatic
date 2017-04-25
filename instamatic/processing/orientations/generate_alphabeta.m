% generate orientations in terms of X, Y, Z; ALPHA, BETA
% polar2xyz(ALPHA, BETA) == XYZ

spacing = 1.7;
syms = {'-1', '2/m', '4/m', 'mmm', '4/mmm', '-3', '6/m', 'm3', '-3m', '6/mmm', 'm3m', 'm-3m'};

for j=1:numel(syms)
    sym = string(syms(j));

    cs = crystalSymmetry(sym);
    ss = crystalSymmetry(sym);
    g = equispacedSO3Grid(cs, ss, 'resolution', spacing*degree);

    xyz = g.alphabeta.xyz;
    theta = g.alphabeta.theta; % alpha
    rho = g.alphabeta.rho;     % beta

    strsym = strrep(sym, '/', 'o');
    fn = sprintf('orientations_%s.txt', strsym);
    f = fopen(fn, 'w');
    for i=1:size(xyz, 1)
        fprintf(f, '% f % f % f % f % f\r\n', xyz(i,1), xyz(i,2), xyz(i,3), theta(i), rho(i));
    end
    fclose(f);
end