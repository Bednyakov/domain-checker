# domain-checker

1. Создай words.txt:
   ```text
   byteforge
   neuralops
   devnexus
   stackcore
   quantumgrid 
   ```

2. Запусти проверку для зоны .dev:
```bash
python domain_checker.py words.txt dev
```

3. Для .com с 50 параллельными проверками:
```bash
python domain_checker.py words.txt com -c 50 -o free.txt
```

Сначала проверяются DNS-записи. Для доменов без DNS выполняется проверка RDAP
через bootstrap-сервис IANA. В файл сохраняются только домены, для которых RDAP
подтвердил отсутствие регистрационной записи. Если RDAP недоступен или не может
проверить домен, он не включается в список кандидатов и выводится отдельно.
