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

## TODO
Добавить проверку RDAP после DNS-проверки для проверки регистрационной записи домена.
