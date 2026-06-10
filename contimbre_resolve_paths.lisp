;; Remnant — risolve ID ConTimbre → path MP3
;; Legge l'indice pre-costruito /tmp/contimbre_mp3_index.txt
;; Costruisci l'indice con:
;;   find "/Volumes/disk 1/conTimbre Standard V2/data/groups" -name "*.mp3" > /tmp/contimbre_mp3_index.txt
;; Uso: sbcl --load contimbre_resolve_paths.lisp

(ql:quickload '(:cl-ppcre) :silent t)

(defvar *index-path* "/tmp/contimbre_mp3_index.txt")
(defvar *score-path*
  (merge-pathnames "brownian_score.json"
    (make-pathname :directory (pathname-directory *load-pathname*))))
(defvar *out-path*   "/tmp/contimbre_paths.json")

(defun escape-json (s)
  (with-output-to-string (out)
    (loop for c across (or s "") do
      (cond ((char= c #\\) (write-string "\\\\" out))
            ((char= c #\") (write-string "\\\"" out))
            (t (write-char c out))))))

(defun filename-no-ext (path-string)
  "Estrae il nome file senza estensione, gestendo nomi con multipli punti.
   pathname-name si ferma al primo punto — questa funzione usa l'ultimo."
  (let* ((slash (position #\/ path-string :from-end t))
         (fname (if slash (subseq path-string (1+ slash)) path-string))
         (dot   (position #\. fname :from-end t)))
    (if dot (subseq fname 0 dot) fname)))

(defun load-index (path)
  "Carica l'indice MP3 in una hash table id→path."
  (let ((ht (make-hash-table :test #'equal :size 100000)))
    (with-open-file (f path)
      (loop for line = (read-line f nil nil)
            while line do
        (let* ((line  (string-trim '(#\Space #\Return) line))
               (fname (filename-no-ext line))
               ;; Rimuove il prefisso licenza dal nome file
               (prefix "usage permitted only with a contimbre.com license ")
               (id    (if (search prefix fname :test #'char=)
                          (subseq fname (length prefix))
                          fname)))
          (setf (gethash id ht) line))))
    ht))

(defun extract-ids-from-json (text)
  "Estrae i valori degli ID dal JSON della score."
  (let ((ids '()))
    (cl-ppcre:do-matches-as-strings
      (m "\"id\"\\s*:\\s*\"([^\"]+)\"" text)
      (let ((id (cl-ppcre:regex-replace
                 "\"id\"\\s*:\\s*\"([^\"]+)\"" m "\\1")))
        (when (and (> (length id) 3)
                   (not (search "~" id))
                   (not (member id ids :test #'string=)))
          (push id ids))))
    (nreverse ids)))

;; Main
(format t "Loading index (~A)...~%" *index-path*)
(let* ((index (load-index *index-path*))
       (text  (with-open-file (f *score-path*)
                (let ((s (make-string (file-length f))))
                  (read-sequence s f) s)))
       (ids   (extract-ids-from-json text))
       (pairs '()))

  (format t "Index: ~A entries~%" (hash-table-count index))
  (format t "Score IDs: ~A~%" (length ids))

  (dolist (id ids)
    (let ((mp3 (gethash id index)))
      (if mp3
        (progn
          (push (format nil "  \"~A\": \"~A\""
                        (escape-json id) (escape-json mp3))
                pairs)
          (format t "  OK: ~A~%" id))
        (format t "  NOT FOUND: ~A~%" id))))

  (with-open-file (f *out-path* :direction :output :if-exists :supersede)
    (format f "{~%~{~A~^,~%~}~%}~%" (nreverse pairs)))

  (format t "~%Saved: ~A (~A paths)~%" *out-path* (length pairs)))

(sb-ext:exit)
